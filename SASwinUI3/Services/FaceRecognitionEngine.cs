using FaceAiSharp;
using FaceAiSharp.Extensions;
using SAS.Models;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;

namespace SAS.Services;

internal sealed class FaceRecognitionEngine
{
    private readonly object _gate = new();
    private readonly IFaceDetector _detector;
    private readonly IFaceEmbeddingsGenerator _embeddings;

    public FaceRecognitionEngine()
    {
        _detector = FaceAiSharpBundleFactory.CreateFaceDetectorWithLandmarks();
        _embeddings = FaceAiSharpBundleFactory.CreateFaceEmbeddingsGenerator();
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
                faceBox);
        }
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
