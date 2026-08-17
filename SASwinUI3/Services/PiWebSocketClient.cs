using System.Net.WebSockets;
using System.Text;
using System.Text.Json.Nodes;

namespace SAS.Services;

public sealed class PiWebSocketClient
{
    public static Uri BuildUri(string host, int apiPort, string clientId, string clientName)
    {
        var query = $"client_id={Uri.EscapeDataString(clientId)}&client_name={Uri.EscapeDataString(clientName)}";
        return new Uri($"ws://{host}:{Math.Clamp(apiPort, 1, 65535)}/ws/sas?{query}");
    }

    public async Task<ClientWebSocket> ConnectAsync(Uri uri, CancellationToken cancellationToken = default)
    {
        var socket = new ClientWebSocket();
        await socket.ConnectAsync(uri, cancellationToken).ConfigureAwait(false);
        return socket;
    }

    public static async Task SendAsync(ClientWebSocket socket, JsonObject payload, CancellationToken cancellationToken = default)
    {
        if (socket.State != WebSocketState.Open)
        {
            return;
        }

        var bytes = Encoding.UTF8.GetBytes(payload.ToJsonString());
        await socket.SendAsync(bytes, WebSocketMessageType.Text, true, cancellationToken).ConfigureAwait(false);
    }

    public static async Task ReceiveTextMessagesAsync(ClientWebSocket socket, Action<string> messageReceived, CancellationToken cancellationToken = default)
    {
        var buffer = new byte[8192];
        using var message = new MemoryStream();
        while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
        {
            message.SetLength(0);
            WebSocketReceiveResult result;
            do
            {
                result = await socket.ReceiveAsync(buffer, cancellationToken).ConfigureAwait(false);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    return;
                }

                message.Write(buffer, 0, result.Count);
            }
            while (!result.EndOfMessage);

            messageReceived(Encoding.UTF8.GetString(message.ToArray()));
        }
    }
}
