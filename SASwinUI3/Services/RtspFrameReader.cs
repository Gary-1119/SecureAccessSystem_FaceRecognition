using OpenCvSharp;

namespace SAS.Services;

internal sealed class RtspFrameReader
{
    private static readonly TimeSpan PreviewFrameInterval = TimeSpan.FromMilliseconds(125);
    private static readonly TimeSpan FrameReadGrace = TimeSpan.FromSeconds(10);

    public async Task ReadAsync(
        string rtspUrl,
        Func<int> getCameraRotation,
        Action onOpened,
        Action<RtspFrame> onFrame,
        CancellationToken cancellationToken)
    {
        Environment.SetEnvironmentVariable(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp|buffer_size;1048576|probesize;1000000|analyzeduration;1000000|max_delay;500000|reorder_queue_size;16|timeout;10000000|rw_timeout;10000000|stimeout;10000000");

        using var capture = new VideoCapture(rtspUrl, VideoCaptureAPIs.FFMPEG);
        capture.Set(VideoCaptureProperties.BufferSize, 4);
        if (!capture.IsOpened())
        {
            throw new InvalidOperationException($"Could not open RTSP stream at {RtspUrlMasker.Mask(rtspUrl)}.");
        }

        onOpened();
        await ReadFramesAsync(capture, getCameraRotation, onFrame, cancellationToken).ConfigureAwait(false);
    }

    private static async Task ReadFramesAsync(
        VideoCapture capture,
        Func<int> getCameraRotation,
        Action<RtspFrame> onFrame,
        CancellationToken cancellationToken)
    {
        using var frame = new Mat();
        var lastPreviewAt = DateTimeOffset.MinValue;
        var lastFrameAt = DateTimeOffset.Now;
        DateTimeOffset? failedReadSince = null;
        while (!cancellationToken.IsCancellationRequested)
        {
            if (!capture.Grab())
            {
                failedReadSince ??= DateTimeOffset.Now;
                if (DateTimeOffset.Now - lastFrameAt < FrameReadGrace &&
                    DateTimeOffset.Now - failedReadSince.Value < FrameReadGrace)
                {
                    await Task.Delay(80, cancellationToken).ConfigureAwait(false);
                    continue;
                }

                throw new InvalidOperationException("RTSP stream stopped returning frames.");
            }

            var capturedAt = DateTimeOffset.Now;
            if (capturedAt - lastPreviewAt < PreviewFrameInterval)
            {
                await Task.Delay(1, cancellationToken).ConfigureAwait(false);
                continue;
            }

            if (!capture.Retrieve(frame) || frame.Empty())
            {
                failedReadSince ??= DateTimeOffset.Now;
                if (DateTimeOffset.Now - lastFrameAt < FrameReadGrace &&
                    DateTimeOffset.Now - failedReadSince.Value < FrameReadGrace)
                {
                    await Task.Delay(80, cancellationToken).ConfigureAwait(false);
                    continue;
                }

                throw new InvalidOperationException("RTSP stream stopped returning frames.");
            }

            lastPreviewAt = capturedAt;
            lastFrameAt = capturedAt;
            failedReadSince = null;
            using var rotated = ApplyRotation(frame, getCameraRotation());
            var jpeg = rotated.ImEncode(".jpg", [new ImageEncodingParam(ImwriteFlags.JpegQuality, 82)]);
            onFrame(new RtspFrame(jpeg.ToArray(), capturedAt));
        }
    }

    private static Mat ApplyRotation(Mat source, int rotation)
    {
        var normalized = NormalizeRotation(rotation);
        if (normalized == 0)
        {
            return source.Clone();
        }

        var rotated = new Mat();
        Cv2.Rotate(source, rotated, normalized switch
        {
            90 => RotateFlags.Rotate90Clockwise,
            180 => RotateFlags.Rotate180,
            270 => RotateFlags.Rotate90Counterclockwise,
            _ => RotateFlags.Rotate90Clockwise
        });
        return rotated;
    }

    public static int NormalizeRotation(int rotation)
    {
        rotation %= 360;
        if (rotation < 0)
        {
            rotation += 360;
        }

        return rotation is 90 or 180 or 270 ? rotation : 0;
    }
}
