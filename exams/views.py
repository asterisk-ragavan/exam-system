from rest_framework import viewsets, permissions, status, views
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
import csv
import io
from .models import Exam, ExamStudent, Question, QuestionOption, StudentAnswer
from .serializers import ExamSerializer, QuestionSerializer, StudentAnswerSerializer
from .forms import QuestionImportForm

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

@login_required
@user_passes_test(is_teacher_or_admin)
def evaluate_attempt(request, attempt_id):
    attempt = get_object_or_404(ExamStudent, id=attempt_id)
    
    # Get all questions for this exam
    # We need to join with StudentAnswer to get the answer if it exists
    questions = attempt.exam.questions.all()
    
    # Fetch answers
    answers = StudentAnswer.objects.filter(exam_student=attempt).select_related('question')
    answers_map = {ans.question_id: ans for ans in answers}
    
    evaluation_data = []
    for q in questions:
        ans = answers_map.get(q.id)
        evaluation_data.append({
            'question': q,
            'answer': ans,
            'options': q.options.all() if q.question_type in [Question.Type.MCQ, Question.Type.MSQ] else None
        })
        
    context = {
        'attempt': attempt,
        'evaluation_data': evaluation_data
    }
    return render(request, 'exams/evaluate_attempt.html', context)

@login_required
@user_passes_test(is_teacher_or_admin)
def import_questions(request):
    if request.method == 'POST':
        form = QuestionImportForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.cleaned_data['course']
            csv_file = request.FILES['csv_file']
            
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'Please upload a CSV file.')
                return render(request, 'exams/import_questions.html', {'form': form})

            try:
                decoded_file = csv_file.read().decode('utf-8-sig') # utf-8-sig handles BOM from Excel
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                
                # Skip header
                next(reader, None)
                
                questions_created = 0
                
                with transaction.atomic():
                    for row in reader:
                        if len(row) < 3:
                            continue
                            
                        text = row[0].strip()
                        if not text:
                            continue

                        difficulty_raw = row[1].strip().upper()
                        difficulty_map = {'E': 'E', 'M': 'M', 'H': 'H', 'EASY': 'E', 'MEDIUM': 'M', 'HARD': 'H'}
                        difficulty = difficulty_map.get(difficulty_raw, 'M')
                        
                        try:
                            marks = int(row[2].strip())
                        except ValueError:
                            marks = 1
                            
                        question = Question.objects.create(
                            course=course,
                            text=text,
                            difficulty=difficulty,
                            marks=marks,
                            question_type=Question.Type.MCQ,
                            created_by=request.user
                        )
                        
                        # Options start from index 3
                        # Format: Option1, IsCorrect1, Option2, IsCorrect2...
                        for i in range(3, len(row), 2):
                            if i + 1 < len(row):
                                opt_text = row[i].strip()
                                if not opt_text:
                                    continue
                                    
                                is_correct_raw = row[i+1].strip().lower()
                                is_correct = is_correct_raw in ['true', '1', 'yes', 't', 'correct']
                                
                                QuestionOption.objects.create(
                                    question=question,
                                    text=opt_text,
                                    is_correct=is_correct
                                )
                        
                        questions_created += 1
                        
                messages.success(request, f'Successfully imported {questions_created} questions.')
                return redirect('teacher_dashboard')
                
            except Exception as e:
                messages.error(request, f'Error processing file: {str(e)}')
                
    else:
        form = QuestionImportForm()
        
    return render(request, 'exams/import_questions.html', {'form': form})

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
            # Generate and store shuffled question order
            questions = list(exam.questions.all())
            if exam.shuffle_questions:
                import random
                random.shuffle(questions)
            attempt.question_order = [q.id for q in questions]
            attempt.save()
            
        # Retrieve questions in stored order
        if attempt.question_order:
            question_ids = attempt.question_order
            questions_dict = {q.id: q for q in exam.questions.all()}
            questions = [questions_dict[qid] for qid in question_ids if qid in questions_dict]
        else:
            # Fallback for existing attempts without stored order
            questions = list(exam.questions.all())
            
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

        # Allow negative total score if negative marking is enabled? 
        # Usually total score shouldn't be negative, but for individual sections it might be.
        # Let's keep it raw for now as per test requirement (which expects -0.5)
        attempt.score_objective = total_objective_score 
        attempt.total_score = attempt.score_objective + attempt.score_subjective
        attempt.save()
        
        return Response({"status": "submitted", "score": attempt.total_score})


from django.http import JsonResponse, HttpResponse
from django.db import models

@login_required
@user_passes_test(is_teacher_or_admin)
def grade_attempt(request, attempt_id):
    if request.method == 'POST':
        attempt = get_object_or_404(ExamStudent, id=attempt_id)
        question_id = request.POST.get('question_id')
        marks = float(request.POST.get('marks', 0))
        
        question = get_object_or_404(Question, id=question_id)
        
        # Update or create answer record (if teacher grades a question student didn't answer)
        answer, created = StudentAnswer.objects.get_or_create(
            exam_student=attempt,
            question=question
        )
        
        answer.marks_awarded = marks
        answer.is_evaluated = True
        answer.save()
        
        # Recalculate subjective score
        subjective_score = StudentAnswer.objects.filter(
            exam_student=attempt, 
            question__question_type__in=[Question.Type.SHORT_ANSWER, Question.Type.LONG_ANSWER, Question.Type.CODE]
        ).aggregate(total=models.Sum('marks_awarded'))['total'] or 0.0
        
        attempt.score_subjective = subjective_score
        attempt.total_score = attempt.score_objective + attempt.score_subjective
        attempt.save()
        
        return JsonResponse({'status': 'success', 'new_total': attempt.total_score})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
@user_passes_test(is_teacher_or_admin)
def export_results(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    attempts = ExamStudent.objects.filter(exam=exam).select_related('student', 'student__student_profile')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{exam.name}_results.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Roll No', 'Name', 'Email', 'Status', 'Objective Score', 'Subjective Score', 'Total Score', 'Submitted At'])
    
    for attempt in attempts:
        student_name = f"{attempt.student.first_name} {attempt.student.last_name}".strip() or attempt.student.username
        roll_no = attempt.student.student_profile.roll_no if hasattr(attempt.student, 'student_profile') else 'N/A'
        
        writer.writerow([
            roll_no,
            student_name,
            attempt.student.email,
            attempt.get_status_display(),
            attempt.score_objective,
            attempt.score_subjective,
            attempt.total_score,
            attempt.submitted_at
        ])
        
    return response
