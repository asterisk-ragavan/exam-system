from django.contrib import admin
from .models import Question, QuestionOption, Exam, ExamQuestion, ExamStudent, StudentAnswer

class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text_preview', 'course', 'question_type', 'difficulty', 'marks', 'is_active')
    list_filter = ('course', 'question_type', 'difficulty', 'is_active')
    search_fields = ('text',)
    inlines = [QuestionOptionInline]

    def text_preview(self, obj):
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text

class ExamQuestionInline(admin.TabularInline):
    model = ExamQuestion
    extra = 1

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'start_datetime', 'duration_minutes', 'status')
    list_filter = ('course', 'status')
    inlines = [ExamQuestionInline]

@admin.register(ExamStudent)
class ExamStudentAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'status', 'total_score', 'started_at', 'submitted_at')
    list_filter = ('status', 'exam')
    search_fields = ('student__username', 'exam__name')

@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ('exam_student', 'question', 'is_evaluated', 'marks_awarded')
    list_filter = ('is_evaluated',)
