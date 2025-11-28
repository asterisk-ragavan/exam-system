from rest_framework import viewsets, permissions, status, views
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Exam, ExamStudent, Question, StudentAnswer
from .serializers import ExamSerializer, QuestionSerializer, StudentAnswerSerializer

# --- Template Views (Teacher Dashboard) ---

def is_teacher_or_admin(user):
    return user.is_authenticated and (user.role == 'TEACHER' or user.role == 'ADMIN')

@login_required
@user_passes_test(is_teacher_or_admin)
def teacher_dashboard(request):
    # Show all exams for now. Later filter by created_by=request.user
    exams = Exam.objects.all().order_by('-start_datetime')
    return render(request, 'exams/teacher_dashboard.html', {'exams': exams})

@login_required
@user_passes_test(is_teacher_or_admin)
def exam_live_status(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    attempts = ExamStudent.objects.filter(exam=exam).select_related('student', 'student__student_profile')
    
    context = {
        'exam': exam,
        'attempts': attempts,
        'total_students': attempts.count(),
        'in_progress_count': attempts.filter(status=ExamStudent.Status.IN_PROGRESS).count(),
        'submitted_count': attempts.filter(status__in=[ExamStudent.Status.SUBMITTED, ExamStudent.Status.AUTO_SUBMITTED]).count(),
        'not_started_count': attempts.filter(status=ExamStudent.Status.NOT_STARTED).count(),
    }
    return render(request, 'exams/exam_live_status.html', context)

# --- Student Template Views ---

@login_required
def student_dashboard(request):
    # Get exams that are SCHEDULED or RUNNING
    # In production, filter by CourseEnrollment
    now = timezone.now()
    active_exams = Exam.objects.filter(
        status__in=[Exam.Status.SCHEDULED, Exam.Status.RUNNING],
        end_datetime__gt=now
    ).order_by('start_datetime')
    
    # Get past attempts
    past_attempts = ExamStudent.objects.filter(
        student=request.user,
        status__in=[ExamStudent.Status.SUBMITTED, ExamStudent.Status.AUTO_SUBMITTED]
    ).order_by('-submitted_at')

    return render(request, 'exams/student_dashboard.html', {
        'active_exams': active_exams,
        'past_attempts': past_attempts
    })

@login_required
def take_exam_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    # Basic validation: is it too early? is it too late?
    now = timezone.now()
    if now < exam.start_datetime:
        return render(request, 'exams/exam_error.html', {'message': 'Exam has not started yet.'})
    if now > exam.end_datetime:
        return render(request, 'exams/exam_error.html', {'message': 'Exam has ended.'})
        
    return render(request, 'exams/take_exam.html', {'exam': exam})

# --- API Views (Student Exam Interface) ---

class ActiveExamsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        # Logic to find exams assigned to this student (via CourseEnrollment)
        # For MVP, let's just return all RUNNING or SCHEDULED exams for courses the student is enrolled in
        # This requires looking up CourseEnrollment, which we'll add later.
        # For now, return all active exams.
        exams = Exam.objects.filter(
            status__in=[Exam.Status.SCHEDULED, Exam.Status.RUNNING],
            end_datetime__gt=now
        )
        serializer = ExamSerializer(exams, many=True)
        return Response(serializer.data)

class StartExamView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, exam_id):
        exam = get_object_or_404(Exam, id=exam_id)
        student = request.user
        
        # Check if already started
        attempt, created = ExamStudent.objects.get_or_create(
            exam=exam,
            student=student
        )
        
        if created:
            attempt.status = ExamStudent.Status.IN_PROGRESS
            attempt.started_at = timezone.now()
            attempt.save()
        
        # Return questions
        # In a real scenario, we would handle shuffling here
        questions = exam.questions.all()
        serializer = QuestionSerializer(questions, many=True)
        
        # Fetch existing answers if resuming
        existing_answers = StudentAnswer.objects.filter(exam_student=attempt)
        answers_map = {
            ans.question.id: {
                'selected_options': ans.selected_options,
                'answer_text': ans.answer_text
            } for ans in existing_answers
        }

        # Calculate accurate remaining time
        now = timezone.now()
        elapsed = (now - attempt.started_at).total_seconds()
        total_seconds = exam.duration_minutes * 60
        remaining_seconds = max(0, total_seconds - elapsed)

        return Response({
            "attempt_id": attempt.id,
            "exam_name": exam.name,
            "questions": serializer.data,
            "saved_answers": answers_map,
            "remaining_seconds": remaining_seconds
        })

class SubmitAnswerView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Expects: { "attempt_id": 1, "question_id": 5, "selected_options": [1, 2], "answer_text": "..." }
        data = request.data
        attempt = get_object_or_404(ExamStudent, id=data.get('attempt_id'), student=request.user)
        
        if attempt.status != ExamStudent.Status.IN_PROGRESS:
            return Response({"error": "Exam is not in progress"}, status=status.HTTP_400_BAD_REQUEST)

        question_id = data.get('question_id')
        question = get_object_or_404(Question, id=question_id)

        answer, created = StudentAnswer.objects.update_or_create(
            exam_student=attempt,
            question=question,
            defaults={
                'selected_options': data.get('selected_options', []),
                'answer_text': data.get('answer_text', '')
            }
        )
        
        return Response({"status": "saved"})

class SubmitExamView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, attempt_id):
        attempt = get_object_or_404(ExamStudent, id=attempt_id, student=request.user)
        
        # Prevent re-submission if already submitted
        if attempt.status in [ExamStudent.Status.SUBMITTED, ExamStudent.Status.AUTO_SUBMITTED]:
             return Response({"status": "already_submitted"})

        attempt.status = ExamStudent.Status.SUBMITTED
        attempt.submitted_at = timezone.now()
        
        # --- Auto Evaluation Logic ---
        total_objective_score = 0.0
        
        # Fetch all answers for this attempt
        student_answers = StudentAnswer.objects.filter(exam_student=attempt).select_related('question')
        
        for ans in student_answers:
            question = ans.question
            if question.question_type in [Question.Type.MCQ, Question.Type.MSQ, Question.Type.TRUE_FALSE]:
                # Get correct option IDs
                correct_options = set(question.options.filter(is_correct=True).values_list('id', flat=True))
                selected_options = set(ans.selected_options) # Assuming list of IDs
                
                # Basic Logic: Full match required for marks (can be improved for partial marking)
                if correct_options == selected_options:
                    ans.marks_awarded = question.marks
                    ans.is_evaluated = True
                    total_objective_score += question.marks
                else:
                    ans.marks_awarded = 0
                    ans.is_evaluated = True
                    # Negative marking check
                    if attempt.exam.negative_marking > 0 and len(selected_options) > 0:
                         total_objective_score -= attempt.exam.negative_marking

                ans.save()

        attempt.score_objective = max(0, total_objective_score) # Ensure no negative total if desired
        attempt.total_score = attempt.score_objective + attempt.score_subjective
        attempt.save()
        
        return Response({"status": "submitted", "score": attempt.total_score})
