from rest_framework import serializers
from .models import Exam, Question, QuestionOption, ExamStudent, StudentAnswer

class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ['id', 'text'] # Don't expose is_correct to students!

class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'text', 'question_type', 'marks', 'options']

class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = ['id', 'name', 'duration_minutes', 'start_datetime', 'end_datetime', 'allow_back_navigation']

class StudentAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAnswer
        fields = ['question', 'selected_options', 'answer_text']

class ExamStudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamStudent
        fields = ['id', 'status', 'started_at', 'submitted_at']
