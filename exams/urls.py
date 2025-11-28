from django.urls import path
from .views import (
    ActiveExamsView, StartExamView, SubmitAnswerView, SubmitExamView,
    teacher_dashboard, exam_live_status, student_dashboard, take_exam_view,
    import_questions
)

urlpatterns = [
    # Template Views
    path('dashboard/', teacher_dashboard, name='teacher_dashboard'),
    path('import-questions/', import_questions, name='import_questions'),
    path('live/<int:exam_id>/', exam_live_status, name='exam_live_status'),
    path('student/dashboard/', student_dashboard, name='student_dashboard'),
    path('take/<int:exam_id>/', take_exam_view, name='take_exam'),

    # API Views
    path('active/', ActiveExamsView.as_view(), name='active-exams'),
    path('start/<int:exam_id>/', StartExamView.as_view(), name='start-exam'),
    path('save-answer/', SubmitAnswerView.as_view(), name='save-answer'),
    path('submit/<int:attempt_id>/', SubmitExamView.as_view(), name='submit-exam'),
]