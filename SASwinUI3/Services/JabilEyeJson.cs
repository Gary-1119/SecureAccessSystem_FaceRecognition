using System.Text.Json.Nodes;

namespace SAS.Services;

public static class JabilEyeJson
{
    public static string ReadString(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is not null)
            {
                if (node is JsonValue value && value.TryGetValue<string>(out var s))
                {
                    return s ?? "";
                }

                return node.ToJsonString();
            }
        }

        return "";
    }

    public static int ReadInt(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is JsonValue value)
            {
                if (value.TryGetValue<int>(out var i)) return i;
                if (value.TryGetValue<long>(out var l)) return (int)l;
                if (value.TryGetValue<string>(out var s) && int.TryParse(s, out var parsed)) return parsed;
            }
        }

        return 0;
    }

    public static long ReadLong(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is JsonValue value)
            {
                if (value.TryGetValue<long>(out var l)) return l;
                if (value.TryGetValue<int>(out var i)) return i;
                if (value.TryGetValue<double>(out var d)) return (long)d;
                if (value.TryGetValue<string>(out var s) && long.TryParse(s, out var parsed)) return parsed;
            }
        }

        return 0;
    }

    public static double ReadDouble(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is JsonValue value)
            {
                if (value.TryGetValue<double>(out var d)) return d;
                if (value.TryGetValue<long>(out var l)) return l;
                if (value.TryGetValue<int>(out var i)) return i;
                if (value.TryGetValue<string>(out var s) && double.TryParse(s, out var parsed)) return parsed;
            }
        }

        return 0;
    }

    public static bool ReadBool(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is JsonValue value)
            {
                if (value.TryGetValue<bool>(out var b)) return b;
                if (value.TryGetValue<string>(out var s) && bool.TryParse(s, out var parsed)) return parsed;
            }
        }

        return false;
    }

    public static IReadOnlyList<string> ReadStringList(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (!data.TryGetPropertyValue(key, out var node) || node is null)
            {
                continue;
            }

            if (node is JsonArray array)
            {
                return array
                    .Select(ReadListItemText)
                    .Where(text => !string.IsNullOrWhiteSpace(text))
                    .ToList();
            }

            if (node is JsonValue scalar && scalar.TryGetValue<string>(out var single) && !string.IsNullOrWhiteSpace(single))
            {
                return [single];
            }
        }

        return [];
    }

    private static string ReadListItemText(JsonNode? item)
    {
        if (item is JsonObject obj)
        {
            return ReadString(obj, "filename", "name", "hostname", "host", "id");
        }

        return item is JsonValue value && value.TryGetValue<string>(out var text)
            ? text
            : item?.ToJsonString() ?? "";
    }
}
