from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=50, choices=Role.choices, default=Role.STUDENT)
    email = models.EmailField(unique=True)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    roll_no = models.CharField(max_length=20, unique=True)
    # We'll link department later to avoid circular imports or use string reference
    department_name = models.CharField(max_length=100, blank=True) 
    batch = models.CharField(max_length=20) # e.g., 2021-2025
    section = models.CharField(max_length=10) # e.g., A, B

    def __str__(self):
        return f"{self.roll_no} - {self.user.username}"

class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    department_name = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.user.username} - {self.designation}"
