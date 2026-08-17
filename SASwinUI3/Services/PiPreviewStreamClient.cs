namespace SAS.Services;

public sealed class PiPreviewStreamClient : IDisposable
{
    private static readonly TimeSpan FrameReadTimeout = TimeSpan.FromSeconds(8);
    private readonly HttpClient _http = new() { Timeout = Timeout.InfiniteTimeSpan };

    public async Task RunAsync(string baseUrl, Action<byte[]> frameAvailable, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(baseUrl))
        {
            throw new InvalidOperationException("Pi hostname/IP is required.");
        }

        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl.TrimEnd('/') + "/video-feed");
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        await ReadMjpegFramesAsync(stream, frameAvailable, cancellationToken).ConfigureAwait(false);
    }

    private static async Task ReadMjpegFramesAsync(Stream stream, Action<byte[]> frameAvailable, CancellationToken cancellationToken)
    {
        var buffer = new byte[8192];
        var frame = new MemoryStream();
        var inJpeg = false;
        var previous = -1;
        while (!cancellationToken.IsCancellationRequested)
        {
            var read = await stream.ReadAsync(buffer, cancellationToken)
                .AsTask()
                .WaitAsync(FrameReadTimeout, cancellationToken)
                .ConfigureAwait(false);
            if (read <= 0)
            {
                return;
            }

            for (var i = 0; i < read; i++)
            {
                var b = buffer[i];
                if (!inJpeg && previous == 0xFF && b == 0xD8)
                {
                    inJpeg = true;
                    frame.SetLength(0);
                    frame.WriteByte(0xFF);
                    frame.WriteByte(0xD8);
                }
                else if (inJpeg)
                {
                    frame.WriteByte(b);
                    if (previous == 0xFF && b == 0xD9)
                    {
                        frameAvailable(frame.ToArray());
                        frame.SetLength(0);
                        inJpeg = false;
                    }
                }

                previous = b;
            }
        }
    }

    public void Dispose()
    {
        _http.Dispose();
    }
}
