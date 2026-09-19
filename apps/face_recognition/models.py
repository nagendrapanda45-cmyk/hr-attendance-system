from django.db import models
from apps.common.models import TimeStampedModel
from apps.employees.models import Employee

class FaceProfile(TimeStampedModel):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ENROLLED', 'Enrolled'),
        ('FAILED', 'Failed'),
    )
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='face_profile')
    enrollment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def __str__(self):
        return f"Face Profile: {self.employee.employee_code}"

class FaceEmbedding(TimeStampedModel):
    face_profile = models.ForeignKey(FaceProfile, on_delete=models.CASCADE, related_name='embeddings')
    embedding_data = models.TextField(help_text="Encrypted or serialized vector data. Do not expose via API.")
    model_version = models.CharField(max_length=50)
    quality_score = models.FloatField(default=0.0)

    def __str__(self):
        return f"Embedding for {self.face_profile.employee.employee_code}"
