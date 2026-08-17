using SAS.Models;

namespace SAS.Services;

internal sealed record FaceEmbeddingResult(
    float[] Embedding,
    RecognitionFaceBox? FaceBox,
    RecognitionEyeState EyeState);
