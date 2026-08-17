using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace SAS.Services;

public sealed class PiApiClient : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(15) };

    public string BaseUrl { get; private set; } = "";

    public void Configure(string baseUrl)
    {
        BaseUrl = baseUrl ?? "";
    }

    public async Task<JsonObject> RequestAsync(string method, string endpoint, JsonObject? payload = null, int timeoutSeconds = 15, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(BaseUrl))
        {
            throw new InvalidOperationException("Pi hostname/IP is required.");
        }

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
        using var request = new HttpRequestMessage(new HttpMethod(method), BuildUrl(endpoint));
        if (payload is not null)
        {
            request.Content = JsonContent.Create(payload, options: JsonOptions);
        }

        using var response = await _http.SendAsync(request, timeoutCts.Token).ConfigureAwait(false);
        var text = await response.Content.ReadAsStringAsync(timeoutCts.Token).ConfigureAwait(false);
        var data = string.IsNullOrWhiteSpace(text) ? new JsonObject() : JsonNode.Parse(text) as JsonObject ?? new JsonObject();
        if (!response.IsSuccessStatusCode)
        {
            var message = PiJson.ReadString(data, "message", "error");
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(message) ? $"Pi API request failed ({(int)response.StatusCode})." : message);
        }

        return data;
    }

    private string BuildUrl(string endpoint)
    {
        endpoint = endpoint.StartsWith('/') ? endpoint : "/" + endpoint;
        return BaseUrl.TrimEnd('/') + endpoint;
    }

    public void Dispose()
    {
        _http.Dispose();
    }
}
