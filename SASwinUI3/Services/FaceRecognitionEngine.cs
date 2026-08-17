using FaceAiSharp;
using FaceAiSharp.Extensions;
using SAS.Models;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;

namespace SAS.Services;

internal sealed class FaceRecognitionEngine
{
    private readonly object _gate = new();
    private readonly IFaceDetector _detector;
    private readonly IFaceEmbeddingsGenerator _embeddings;
    private readonly IEyeStateDetector _eyeStateDetector;

    public FaceRecognitionEngine()
    {
        _detector = FaceAiSharpBundleFactory.CreateFaceDetectorWithLandmarks();
        _embeddings = FaceAiSharpBundleFactory.CreateFaceEmbeddingsGenerator();
        _eyeStateDetector = FaceAiSharpBundleFactory.CreateEyeStateDetector();
    }

    public FaceEmbeddingResult GenerateBestEmbedding(byte[] jpeg)
    {
        lock (_gate)
        {
            using var image = Image.Load<Rgb24>(jpeg);
            var faces = _detector.DetectFaces(image)
                .OrderByDescending(face => face.Confidence ?? 0f)
                .ToList();
            if (faces.Count == 0)
            {
                throw new InvalidOperationException("No face was detected in the current camera frame.");
            }

            var bestFace = faces[0];
            if (bestFace.Landmarks is null || bestFace.Landmarks.Count == 0)
            {
                throw new InvalidOperationException("Face was detected, but no facial landmarks were available for alignment.");
            }

            var faceImage = image.Clone();
            _embeddings.AlignFaceUsingLandmarks(faceImage, bestFace.Landmarks);
            var faceBox = BuildFaceBoxFromLandmarks(bestFace.Landmarks, image.Width, image.Height);
            return new FaceEmbeddingResult(
                ToFloatArray(_embeddings.GenerateEmbedding(faceImage)),
                faceBox,
                DetectEyeState(image, bestFace.Landmarks));
        }
    }

    private RecognitionEyeState DetectEyeState(Image<Rgb24> image, IReadOnlyList<SixLabors.ImageSharp.PointF> landmarks)
    {
        if (landmarks.Count < 2)
        {
            return new RecognitionEyeState(false, false, false);
        }

        var leftEye = landmarks[0];
        var rightEye = landmarks[1];
        var eyeDistance = Math.Max(8d, Distance(leftEye, rightEye));
        var side = Math.Max(24, eyeDistance * 0.74d);
        using var leftCrop = CropSquare(image, leftEye, side);
        using var rightCrop = CropSquare(image, rightEye, side);
        var leftOpen = _eyeStateDetector.IsOpen(leftCrop);
        var rightOpen = _eyeStateDetector.IsOpen(rightCrop);
        return new RecognitionEyeState(true, leftOpen, rightOpen);
    }

    private static RecognitionFaceBox BuildFaceBoxFromLandmarks(IReadOnlyList<SixLabors.ImageSharp.PointF> landmarks, int imageWidth, int imageHeight)
    {
        var minX = landmarks.Min(point => point.X);
        var maxX = landmarks.Max(point => point.X);
        var minY = landmarks.Min(point => point.Y);
        var maxY = landmarks.Max(point => point.Y);
        var spanX = Math.Max(1, maxX - minX);
        var spanY = Math.Max(1, maxY - minY);
        var centerX = (minX + maxX) / 2d;
        var centerY = (minY + maxY) / 2d + spanY * 0.15d;
        var boxWidth = Math.Min(imageWidth, spanX * 3.4d);
        var boxHeight = Math.Min(imageHeight, spanY * 4.2d);
        var left = Math.Clamp(centerX - boxWidth / 2d, 0, Math.Max(0, imageWidth - boxWidth));
        var top = Math.Clamp(centerY - boxHeight * 0.45d, 0, Math.Max(0, imageHeight - boxHeight));

        return new RecognitionFaceBox(
            left / imageWidth,
            top / imageHeight,
            boxWidth / imageWidth,
            boxHeight / imageHeight);
    }

    private static Image<Rgb24> CropSquare(Image<Rgb24> image, SixLabors.ImageSharp.PointF center, double side)
    {
        var size = Math.Max(1, (int)Math.Round(side));
        var left = (int)Math.Round(center.X - size / 2d);
        var top = (int)Math.Round(center.Y - size / 2d);
        left = Math.Clamp(left, 0, Math.Max(0, image.Width - size));
        top = Math.Clamp(top, 0, Math.Max(0, image.Height - size));
        size = Math.Min(size, Math.Min(image.Width - left, image.Height - top));
        var crop = image.Clone();
        crop.Mutate(context => context.Crop(new SixLabors.ImageSharp.Rectangle(left, top, size, size)));
        return crop;
    }

    private static double Distance(SixLabors.ImageSharp.PointF a, SixLabors.ImageSharp.PointF b)
    {
        var dx = a.X - b.X;
        var dy = a.Y - b.Y;
        return Math.Sqrt(dx * dx + dy * dy);
    }

    private static float[] ToFloatArray(object embedding)
    {
        if (embedding is float[] floats)
        {
            return floats;
        }

        if (embedding is IEnumerable<float> enumerable)
        {
            return enumerable.ToArray();
        }

        var values = embedding.GetType().GetProperty("Values")?.GetValue(embedding);
        if (values is IEnumerable<float> valueEnumerable)
        {
            return valueEnumerable.ToArray();
        }

        throw new InvalidOperationException("FaceAiSharp returned an unsupported embedding format.");
    }
}
