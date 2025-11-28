from django.db import models
from django.conf import settings
from academics.models import Course

class Question(models.Model):
    class Type(models.TextChoices):
        MCQ = "MCQ", "Multiple Choice"
        MSQ = "MSQ", "Multiple Select"
        TRUE_FALSE = "TRUE_FALSE", "True/False"
        SHORT_ANSWER = "SHORT", "Short Answer"
        LONG_ANSWER = "LONG", "Long Answer"
        CODE = "CODE", "Code Snippet"

    class Difficulty(models.TextChoices):
        EASY = "E", "Easy"
        MEDIUM = "M", "Medium"
        HARD = "H", "Hard"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    question_type = models.CharField(max_length=20, choices=Type.choices, default=Type.MCQ)
    marks = models.PositiveIntegerField(default=1)
    difficulty = models.CharField(max_length=1, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.text[:50]}..."

class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text

class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SCHEDULED = "SCHEDULED", "Scheduled"
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"

    name = models.CharField(max_length=200)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='exams')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    duration_minutes = models.PositiveIntegerField()
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField() # Includes grace period
    
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    allow_back_navigation = models.BooleanField(default=True)
    negative_marking = models.FloatField(default=0.0) # e.g. 0.25
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    questions = models.ManyToManyField(Question, through='ExamQuestion')

    def __str__(self):
        return self.name

class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    marks_override = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['order']

class ExamStudent(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not Started"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        SUBMITTED = "SUBMITTED", "Submitted"
        AUTO_SUBMITTED = "AUTO_SUBMITTED", "Auto Submitted"

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_attempts')
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    score_objective = models.FloatField(default=0.0)
    score_subjective = models.FloatField(default=0.0)
    total_score = models.FloatField(default=0.0)
    
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    # Store shuffled question order (list of question IDs)
    question_order = models.JSONField(default=list, blank=True)
    
    # Security logs
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    def __str__(self):
        return f"{self.student} - {self.exam}"

class StudentAnswer(models.Model):
    exam_student = models.ForeignKey(ExamStudent, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    
    # For MCQ/MSQ - store list of option IDs as JSON or comma-separated
    selected_options = models.JSONField(default=list, blank=True) 
    
    # For Subjective
    answer_text = models.TextField(blank=True)
    
    is_evaluated = models.BooleanField(default=False)
    marks_awarded = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('exam_student', 'question')
