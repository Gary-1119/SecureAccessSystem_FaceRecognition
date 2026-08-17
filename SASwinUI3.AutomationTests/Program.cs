using System.Text.Json.Nodes;
using SAS.Controllers;
using SAS.Models;
using SAS.Services;

namespace SASwinUI3.AutomationTests;

internal static class Program
{
    private static readonly List<(string Name, Func<Task> Test)> Tests =
    [
        ("AppSettings cleans host names and builds API URLs", TestAppSettingsHostNormalization),
        ("AppSettings clone isolates mutable hostname changes", TestAppSettingsCloneIsolation),
        ("JabilEyeJson reads string lists from object arrays", TestJabilEyeJsonStringListObjectArrays),
        ("FaceDataController validates local ZIP import", TestFaceDataLocalZipValidation),
        ("FaceDataController builds temporary SMB settings without leaking credentials into base settings", TestFaceDataTemporaryServerSettings),
        ("FaceDataController normalizes SMB paths and mounted ZIP paths", TestFaceDataPathHelpers),
        ("JabilEyeConnectionController does not treat disconnected as connected", TestDisconnectedStateIsNotConnected),
        ("JabilEyeConnectionController stops old session before reconnect", TestJabilEyeConnectionStopsOldSessionBeforeConnect),
        ("JabilEyeConnectionController reports wrong hostname as disconnected", TestJabilEyeConnectionWrongHostnameFails),
        ("UserAuthService first valid sign-in becomes admin", TestFirstSignInBecomesAdmin)
    ];

    public static async Task<int> Main()
    {
        var failures = new List<string>();
        foreach (var (name, test) in Tests)
        {
            try
            {
                await test();
                Console.WriteLine($"PASS {name}");
            }
            catch (Exception ex)
            {
                failures.Add($"{name}: {ex.Message}");
                Console.WriteLine($"FAIL {name}");
                Console.WriteLine(ex);
            }
        }

        Console.WriteLine();
        Console.WriteLine($"{Tests.Count - failures.Count}/{Tests.Count} automation tests passed.");
        if (failures.Count == 0)
        {
            return 0;
        }

        Console.WriteLine("Failures:");
        foreach (var failure in failures)
        {
            Console.WriteLine($"- {failure}");
        }

        return 1;
    }

    private static Task TestAppSettingsHostNormalization()
    {
        AssertEqual("JEFACE", AppSettings.CleanHost(" http://JEFACE:5000/path "));
        AssertEqual("192.168.1.25", AppSettings.CleanHost("rtsp://192.168.1.25:8554/jabileye-stream"));
        AssertEqual("mypenrpieye058", AppSettings.CleanHost("rtsp://admin:penAteam@mypenrpieye058:8554/jabileye-stream"));

        var settings = new AppSettings { CameraHost = "https://JEFACEDESKTOP:5000/api", ApiPort = 5000 };
        AssertEqual("JEFACEDESKTOP", settings.JabilEyeHost);
        AssertEqual("http://JEFACEDESKTOP:5000", settings.ApiBaseUrl);
        return Task.CompletedTask;
    }

    private static Task TestAppSettingsCloneIsolation()
    {
        var settings = new AppSettings
        {
            CameraHost = "JEFACEDESKTOP",
            ServerUsername = "USERA",
            ServerPassword = "secret",
            DisableKeyboardWhenLocked = true
        };
        var clone = settings.Clone();
        settings.CameraHost = "JEFACE";
        settings.ServerPassword = "changed";

        AssertEqual("JEFACEDESKTOP", clone.CameraHost);
        AssertEqual("secret", clone.ServerPassword);
        AssertTrue(clone.DisableKeyboardWhenLocked, "Clone should preserve lock settings.");
        return Task.CompletedTask;
    }

    private static Task TestJabilEyeJsonStringListObjectArrays()
    {
        var data = new JsonObject
        {
            ["pending"] = new JsonArray
            {
                new JsonObject { ["filename"] = "backup_before_import_20260729.zip", ["modified"] = 1785300000 },
                new JsonObject { ["name"] = "face_data.zip" },
                "plain.zip"
            }
        };

        var values = JabilEyeJson.ReadStringList(data, "pending");
        AssertSequence(["backup_before_import_20260729.zip", "face_data.zip", "plain.zip"], values);
        return Task.CompletedTask;
    }

    private static async Task TestFaceDataLocalZipValidation()
    {
        var transfer = new FakeJabilEyeTransferService();
        var controller = new FaceDataController(transfer, CreateLogService());

        await AssertThrowsAsync<FaceDataValidationException>(() =>
            controller.ImportAsync(new FaceDataImportRequest(true, "C:/Temp/not-a-zip.txt", null)));

        AssertFalse(transfer.ImportLocalCalled, "Invalid local import must not call transfer service.");
    }

    private static Task TestFaceDataTemporaryServerSettings()
    {
        var baseSettings = new AppSettings
        {
            CameraHost = "JEFACEDESKTOP",
            ApiPort = 5000,
            ServerUsername = "OWNER",
            ServerPassword = "owner-password",
            ServerPath = "//owner/share",
            ClientId = "client-1"
        };

        var temporary = FaceDataController.CreateTemporaryServerSettings(baseSettings, " TEAMMATE ", "team-password", @"\\server\share\face_data.zip");
        AssertNotNull(temporary, "Temporary SMB settings should be created.");
        AssertEqual("JEFACEDESKTOP", temporary!.CameraHost);
        AssertEqual("TEAMMATE", temporary.ServerUsername);
        AssertEqual("team-password", temporary.ServerPassword);
        AssertEqual("//server/share/face_data.zip", temporary.ServerPath);
        AssertEqual("OWNER", baseSettings.ServerUsername);
        AssertEqual("owner-password", baseSettings.ServerPassword);
        return Task.CompletedTask;
    }

    private static Task TestFaceDataPathHelpers()
    {
        AssertEqual("//server/share/folder", FaceDataController.GetServerMountPathFromImportPath(@"\\server\share\folder\backup.zip"));
        AssertEqual("//server/share/folder", FaceDataController.NormalizeServerPath(@"\\server\share\folder"));
        return Task.CompletedTask;
    }

    private static Task TestDisconnectedStateIsNotConnected()
    {
        var status = new RecognitionStatus(
            true,
            false,
            true,
            "disconnected",
            "This JabilEye is already connected with another SAS device.",
            "http://JEFACE:5000",
            1,
            null,
            null,
            null,
            null);

        AssertFalse(JabilEyeConnectionController.IsEffectivelyConnected(status), "Disconnected must not match the connected state.");
        return Task.CompletedTask;
    }

    private static async Task TestJabilEyeConnectionStopsOldSessionBeforeConnect()
    {
        var recognition = new FakeRecognitionService
        {
            Status = new RecognitionStatus(true, true, true, "live", "", "http://old:5000", 0, DateTimeOffset.Now, null, null, null)
        };
        var controller = new JabilEyeConnectionController(recognition, CreateLogService());

        var result = await controller.ConnectAsync(new AppSettings { CameraHost = "JEFACE", ApiPort = 5000 }, waitTimeout: TimeSpan.FromMilliseconds(50));

        AssertTrue(result.Connected, "Connection should succeed when fake service publishes a fresh frame.");
        AssertEqual(1, recognition.StopCount);
        AssertEqual("JEFACE", recognition.ConfiguredSettings.JabilEyeHost);
    }

    private static async Task TestJabilEyeConnectionWrongHostnameFails()
    {
        var recognition = new FakeRecognitionService { StartPublishesFrame = false };
        var controller = new JabilEyeConnectionController(recognition, CreateLogService());

        var result = await controller.ConnectAsync(new AppSettings { CameraHost = "WRONGHOST", ApiPort = 5000 }, waitTimeout: TimeSpan.FromMilliseconds(50));

        AssertFalse(result.Connected, "Wrong hostname should not report connected.");
        AssertEqual("WRONGHOST", recognition.ConfiguredSettings.JabilEyeHost);
    }

    private static Task TestFirstSignInBecomesAdmin()
    {
        var originalLocalAppData = Environment.GetEnvironmentVariable("LOCALAPPDATA");
        var root = Path.Combine(Path.GetTempPath(), "SAS_AUTH_TESTS", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            Environment.SetEnvironmentVariable("LOCALAPPDATA", root);
            var auth = new UserAuthService();
            var admin = auth.SignIn("admin", "penAteam");
            AssertTrue(admin.IsAdmin, "Developer emergency account should sign in as admin.");
            AssertEqual("ADMIN", admin.Ntid);
        }
        finally
        {
            Environment.SetEnvironmentVariable("LOCALAPPDATA", originalLocalAppData);
            Directory.Delete(root, recursive: true);
        }

        return Task.CompletedTask;
    }

    private static AppLogService CreateLogService()
    {
        return new AppLogService(action => action());
    }

    private static void AssertTrue(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private static void AssertFalse(bool condition, string message)
    {
        AssertTrue(!condition, message);
    }

    private static void AssertNotNull<T>(T? value, string message)
    {
        if (value is null)
        {
            throw new InvalidOperationException(message);
        }
    }

    private static void AssertEqual<T>(T expected, T actual)
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
        {
            throw new InvalidOperationException($"Expected '{expected}', got '{actual}'.");
        }
    }

    private static void AssertSequence<T>(IEnumerable<T> expected, IEnumerable<T> actual)
    {
        var expectedList = expected.ToList();
        var actualList = actual.ToList();
        if (expectedList.Count != actualList.Count)
        {
            throw new InvalidOperationException($"Expected {expectedList.Count} items, got {actualList.Count}.");
        }

        for (var i = 0; i < expectedList.Count; i++)
        {
            if (!EqualityComparer<T>.Default.Equals(expectedList[i], actualList[i]))
            {
                throw new InvalidOperationException($"Item {i}: expected '{expectedList[i]}', got '{actualList[i]}'.");
            }
        }
    }

    private static async Task AssertThrowsAsync<TException>(Func<Task> action)
        where TException : Exception
    {
        try
        {
            await action();
        }
        catch (TException)
        {
            return;
        }

        throw new InvalidOperationException($"Expected exception {typeof(TException).Name}.");
    }
}
