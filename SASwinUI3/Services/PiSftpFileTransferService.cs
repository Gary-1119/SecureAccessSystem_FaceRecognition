using System.Net.Sockets;
using Renci.SshNet;

namespace SAS.Services;

public sealed class PiSftpFileTransferService
{
    public async Task DownloadAsync(string host, string username, string password, string remotePath, string localPath, CancellationToken cancellationToken = default)
    {
        await Task.Run(() =>
        {
            using var client = CreateClient(host, username, password);
            client.Connect();
            Directory.CreateDirectory(Path.GetDirectoryName(localPath)!);
            using var output = File.Create(localPath);
            client.DownloadFile(remotePath, output);
            client.Disconnect();
        }, cancellationToken).ConfigureAwait(false);
    }

    public async Task UploadAsync(string host, string username, string password, string localPath, string remotePath, CancellationToken cancellationToken = default)
    {
        await Task.Run(() =>
        {
            using var client = CreateClient(host, username, password);
            client.Connect();
            using var input = File.OpenRead(localPath);
            client.UploadFile(input, remotePath, canOverride: true);
            client.Disconnect();
        }, cancellationToken).ConfigureAwait(false);
    }

    public static async Task EnsureReachableAsync(string hostname, CancellationToken cancellationToken = default)
    {
        hostname = CleanHost(hostname);
        if (string.IsNullOrWhiteSpace(hostname))
        {
            throw new InvalidOperationException("Target hostname/IP is required.");
        }

        using var client = new TcpClient();
        var connectTask = client.ConnectAsync(hostname, 22, cancellationToken).AsTask();
        var finished = await Task.WhenAny(connectTask, Task.Delay(TimeSpan.FromSeconds(5), cancellationToken)).ConfigureAwait(false);
        if (finished != connectTask || !client.Connected)
        {
            throw new InvalidOperationException($"{hostname} is not reachable on SFTP port 22.");
        }
    }

    public static string CombineUnixPath(string folder, string file)
    {
        return $"{folder.TrimEnd('/')}/{file}";
    }

    private static SftpClient CreateClient(string host, string username, string password)
    {
        var client = new SftpClient(host, 22, username, password);
        client.ConnectionInfo.Timeout = TimeSpan.FromSeconds(15);
        return client;
    }

    private static string CleanHost(string host)
    {
        host = (host ?? "").Trim();
        foreach (var prefix in new[] { "http://", "https://", "ssh://", "sftp://" })
        {
            if (host.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                host = host[prefix.Length..];
                break;
            }
        }

        return host.Split('/')[0].Split(':')[0].Trim();
    }
}
