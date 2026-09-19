from rest_framework import serializers

class FaceEnrollmentSerializer(serializers.Serializer):
    # Support multiple samples. If only one image is sent, it can be passed as a single string,
    # but we will standardize on a list of base64 strings to support "front", "left", "right" variations.
    images_base64 = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        max_length=5,
        help_text="List of Base64 encoded image strings."
    )


class FaceRecognitionSerializer(serializers.Serializer):
    image_base64 = serializers.CharField(required=True, help_text="Base64 encoded image string for recognition.")

class FaceLivenessSerializer(serializers.Serializer):
    frames_base64 = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text="Array of Base64 encoded image frames for liveness detection."
    )
