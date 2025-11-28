from django.db import models
from django.conf import settings

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True) # e.g. CSE, ECE

    def __str__(self):
        return self.name

class Course(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True) # e.g. CS101
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='courses')
    semester = models.IntegerField()

    def __str__(self):
        return f"{self.code} - {self.name}"

class CourseEnrollment(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    section = models.CharField(max_length=10, blank=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student} -> {self.course}"
