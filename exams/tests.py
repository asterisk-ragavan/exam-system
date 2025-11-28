from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import models
from django.urls import reverse
from datetime import timedelta
from academics.models import Department, Course, CourseEnrollment
from users.models import StudentProfile
from exams.models import Exam, Question, QuestionOption, ExamStudent, StudentAnswer

User = get_user_model()

class MVPPhase1Tests(TestCase):
    def setUp(self):
        # 1. Setup Users
        self.admin = User.objects.create_superuser(username='admin', email='admin@test.com', password='password')
        self.teacher = User.objects.create_user(username='teacher', email='teacher@test.com', password='password', role=User.Role.TEACHER)
        
        # Student with full details for UI tests
        self.student = User.objects.create_user(
            username='student', 
            email='student@test.com', 
            password='password', 
            role=User.Role.STUDENT,
            first_name='John',
            last_name='Doe'
        )
        self.student_profile = StudentProfile.objects.create(user=self.student, roll_no="STU001", batch="2024", section="A")

        self.student2 = User.objects.create_user(username='student2', email='student2@test.com', password='password', role=User.Role.STUDENT)

        # 2. Setup Academics
        self.dept = Department.objects.create(name="CSE", code="CSE")
        self.course = Course.objects.create(name="Python Basics", code="CS101", department=self.dept, semester=1)
        
        # Enroll student
        CourseEnrollment.objects.create(student=self.student, course=self.course, section="A")

        # 3. Setup Question Bank (MCQ)
        self.q1 = Question.objects.create(course=self.course, text="What is 2+2?", marks=1, question_type=Question.Type.MCQ, created_by=self.teacher)
        self.q1_opt_a = QuestionOption.objects.create(question=self.q1, text="3", is_correct=False)
        self.q1_opt_b = QuestionOption.objects.create(question=self.q1, text="4", is_correct=True)

    # --- Feature: User roles & login ---
    def test_user_roles_and_login(self):
        """Test that users have correct roles and can login"""
        self.assertEqual(self.teacher.role, User.Role.TEACHER)
        self.assertEqual(self.student.role, User.Role.STUDENT)
        
        # Test Login
        self.client.login(username='student', password='password')
        response = self.client.get(reverse('index'))
        # Should redirect to student dashboard
        self.assertRedirects(response, reverse('student-dashboard'))
        self.client.logout()

        self.client.login(username='teacher', password='password')
        response = self.client.get(reverse('index'))
        # Should redirect to teacher dashboard
        self.assertRedirects(response, reverse('teacher-dashboard'))

    # --- Feature: Course & student management ---
    def test_course_and_student_management(self):
        """Test course creation and student enrollment"""
        self.assertEqual(self.course.name, "Python Basics")
        self.assertEqual(CourseEnrollment.objects.count(), 1)
        self.assertEqual(self.student.enrollments.first().course, self.course)
        self.assertEqual(self.student.student_profile.roll_no, "STU001")

    # --- Feature: Question bank with MCQ only ---
    def test_question_bank_mcq(self):
        """Test MCQ question creation and options"""
        self.assertEqual(self.q1.question_type, Question.Type.MCQ)
        self.assertEqual(self.q1.options.count(), 2)
        correct_option = self.q1.options.get(is_correct=True)
        self.assertEqual(correct_option.text, "4")

    # --- Feature: Exam creation ---
    def test_exam_creation(self):
        """Test exam creation with fixed questions, duration, start time"""
        start_time = timezone.now() + timedelta(hours=1)
        exam = Exam.objects.create(
            name="Mid Term",
            course=self.course,
            duration_minutes=90,
            start_datetime=start_time,
            end_datetime=start_time + timedelta(hours=2),
            status=Exam.Status.SCHEDULED,
            created_by=self.teacher
        )
        # Add fixed set of questions
        exam.questions.add(self.q1)
        
        self.assertEqual(exam.duration_minutes, 90)
        self.assertEqual(exam.questions.count(), 1)
        self.assertEqual(exam.status, Exam.Status.SCHEDULED)

    # --- Feature: Student exam UI (Backend Logic) ---
    def test_student_exam_ui_logic(self):
        """Test Timer, Autosave logic via API"""
        # Create running exam
        exam = Exam.objects.create(
            name="Live Exam",
            course=self.course,
            duration_minutes=60,
            start_datetime=timezone.now() - timedelta(minutes=10),
            end_datetime=timezone.now() + timedelta(minutes=50),
            status=Exam.Status.RUNNING
        )
        exam.questions.add(self.q1)

        self.client.login(username='student', password='password')
        
        # 1. Start Exam (Timer check)
        response = self.client.post(reverse('start-exam', args=[exam.id]))
        data = response.json()
        
        # The attempt starts NOW, so remaining time should be full duration (60 mins = 3600s)
        # We allow a small delta for execution time
        self.assertAlmostEqual(data['remaining_seconds'], 3600, delta=10)
        attempt_id = data['attempt_id']

        # 2. Autosave (Next/Prev logic simulation)
        response = self.client.post(reverse('save-answer'), {
            'attempt_id': attempt_id,
            'question_id': self.q1.id,
            'selected_options': [self.q1_opt_b.id]
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        # Verify saved
        saved_ans = StudentAnswer.objects.get(exam_student_id=attempt_id, question=self.q1)
        self.assertIn(self.q1_opt_b.id, saved_ans.selected_options)

    # --- Feature: Auto-evaluation & Results View ---
    def test_auto_evaluation_and_teacher_view(self):
        """Test auto-grading and teacher results view"""
        # Create running exam
        exam = Exam.objects.create(
            name="Graded Exam",
            course=self.course,
            duration_minutes=60,
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(hours=1),
            status=Exam.Status.RUNNING
        )
        exam.questions.add(self.q1)

        # Student takes exam
        self.client.login(username='student', password='password')
        response = self.client.post(reverse('start-exam', args=[exam.id]))
        attempt_id = response.json()['attempt_id']
        
        # Submit Correct Answer
        self.client.post(reverse('save-answer'), {
            'attempt_id': attempt_id,
            'question_id': self.q1.id,
            'selected_options': [self.q1_opt_b.id]
        }, content_type='application/json')
        
        # Submit Exam
        self.client.post(reverse('submit-exam', args=[attempt_id]))
        
        # Verify Score (Auto-evaluation)
        attempt = ExamStudent.objects.get(id=attempt_id)
        self.assertEqual(attempt.score_objective, 1.0)
        self.assertEqual(attempt.status, ExamStudent.Status.SUBMITTED)

        # Verify Teacher View (Simple results)
        self.client.logout()
        self.client.login(username='teacher', password='password')
        
        response = self.client.get(reverse('exam-live-status', args=[exam.id]))
        self.assertEqual(response.status_code, 200)
        # Check if student name and score appear in the HTML
        self.assertContains(response, "John Doe") # First/Last name
        self.assertContains(response, "1.0") # Score

class ExamFlowTest(TestCase):
    def setUp(self):
        # 1. Setup Users
        self.teacher = User.objects.create_user(username='teacher_flow', email='teacher_flow@test.com', password='password', role=User.Role.TEACHER)
        self.student = User.objects.create_user(username='student_flow', email='student_flow@test.com', password='password', role=User.Role.STUDENT)

        # 2. Setup Academics

    # --- Feature: User roles & login ---
    def test_user_roles_and_login(self):
        """Test that users have correct roles and can login"""
        self.assertEqual(self.teacher.role, User.Role.TEACHER)
        self.assertEqual(self.student.role, User.Role.STUDENT)
        
        # Test Login
        self.client.login(username='student', password='password')
        response = self.client.get(reverse('index'))
        # Should redirect to student dashboard
        self.assertRedirects(response, reverse('student-dashboard'))
        self.client.logout()

        self.client.login(username='teacher', password='password')
        response = self.client.get(reverse('index'))
        # Should redirect to teacher dashboard
        self.assertRedirects(response, reverse('teacher-dashboard'))

    # --- Feature: Course & student management ---
    def test_course_and_student_management(self):
        """Test course creation and student enrollment"""
        self.assertEqual(self.course.name, "Python Basics")
        self.assertEqual(CourseEnrollment.objects.count(), 1)
        self.assertEqual(self.student.enrollments.first().course, self.course)

    # --- Feature: Question bank with MCQ only ---
    def test_question_bank_mcq(self):
        """Test MCQ question creation and options"""
        self.assertEqual(self.q1.question_type, Question.Type.MCQ)
        self.assertEqual(self.q1.options.count(), 2)
        correct_option = self.q1.options.get(is_correct=True)
        self.assertEqual(correct_option.text, "4")

    # --- Feature: Exam creation ---
    def test_exam_creation(self):
        """Test exam creation with fixed questions, duration, start time"""
        start_time = timezone.now() + timedelta(hours=1)
        exam = Exam.objects.create(
            name="Mid Term",
            course=self.course,
            duration_minutes=90,
            start_datetime=start_time,
            end_datetime=start_time + timedelta(hours=2),
            status=Exam.Status.SCHEDULED,
            created_by=self.teacher
        )
        # Add fixed set of questions
        exam.questions.add(self.q1)
        
        self.assertEqual(exam.duration_minutes, 90)
        self.assertEqual(exam.questions.count(), 1)
        self.assertEqual(exam.status, Exam.Status.SCHEDULED)

    # --- Feature: Student exam UI (Backend Logic) ---
    def test_student_exam_ui_logic(self):
        """Test Timer, Autosave logic via API"""
        # Create running exam
        exam = Exam.objects.create(
            name="Live Exam",
            course=self.course,
            duration_minutes=60,
            start_datetime=timezone.now() - timedelta(minutes=10),
            end_datetime=timezone.now() + timedelta(minutes=50),
            status=Exam.Status.RUNNING
        )
        exam.questions.add(self.q1)

        self.client.login(username='student', password='password')
        
        # 1. Start Exam (Timer check)
        response = self.client.post(reverse('start-exam', args=[exam.id]))
        data = response.json()
        # Remaining seconds should be approx 50 mins (3000s)
        self.assertAlmostEqual(data['remaining_seconds'], 3000, delta=10)
        attempt_id = data['attempt_id']

        # 2. Autosave (Next/Prev logic simulation)
        response = self.client.post(reverse('save-answer'), {
            'attempt_id': attempt_id,
            'question_id': self.q1.id,
            'selected_options': [self.q1_opt_b.id]
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        # Verify saved
        saved_ans = StudentAnswer.objects.get(exam_student_id=attempt_id, question=self.q1)
        self.assertIn(self.q1_opt_b.id, saved_ans.selected_options)

    # --- Feature: Auto-evaluation & Results View ---
    def test_auto_evaluation_and_teacher_view(self):
        """Test auto-grading and teacher results view"""
        # Create running exam
        exam = Exam.objects.create(
            name="Graded Exam",
            course=self.course,
            duration_minutes=60,
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(hours=1),
            status=Exam.Status.RUNNING
        )
        exam.questions.add(self.q1)

        # Student takes exam
        self.client.login(username='student', password='password')
        response = self.client.post(reverse('start-exam', args=[exam.id]))
        attempt_id = response.json()['attempt_id']
        
        # Submit Correct Answer
        self.client.post(reverse('save-answer'), {
            'attempt_id': attempt_id,
            'question_id': self.q1.id,
            'selected_options': [self.q1_opt_b.id]
        }, content_type='application/json')
        
        # Submit Exam
        self.client.post(reverse('submit-exam', args=[attempt_id]))
        
        # Verify Score (Auto-evaluation)
        attempt = ExamStudent.objects.get(id=attempt_id)
        self.assertEqual(attempt.score_objective, 1.0)
        self.assertEqual(attempt.status, ExamStudent.Status.SUBMITTED)

        # Verify Teacher View (Simple results)
        self.client.logout()
        self.client.login(username='teacher', password='password')
        
        response = self.client.get(reverse('exam-live-status', args=[exam.id]))
        self.assertEqual(response.status_code, 200)
        # Check if student name and score appear in the HTML
        self.assertContains(response, "student")
        self.assertContains(response, "1.0") # Score

class ExamFlowTest(TestCase):
    def setUp(self):
        # 1. Setup Users
        self.teacher = User.objects.create_user(username='teacher_flow', email='teacher_flow@test.com', password='password', role=User.Role.TEACHER)
        self.student = User.objects.create_user(username='student_flow', email='student_flow@test.com', password='password', role=User.Role.STUDENT)

        # 2. Setup Academics
        self.dept = Department.objects.create(name="CSE", code="CSE")
        self.course = Course.objects.create(name="Python Basics", code="CS101", department=self.dept, semester=1)

        # 3. Setup Questions (2 MCQs)
        # Q1: 1 Mark, Correct Option: B
        self.q1 = Question.objects.create(course=self.course, text="What is 2+2?", marks=1, question_type=Question.Type.MCQ)
        self.q1_opt_a = QuestionOption.objects.create(question=self.q1, text="3", is_correct=False)
        self.q1_opt_b = QuestionOption.objects.create(question=self.q1, text="4", is_correct=True)
        
        # Q2: 2 Marks, Correct Option: A
        self.q2 = Question.objects.create(course=self.course, text="Is Python compiled?", marks=2, question_type=Question.Type.MCQ)
        self.q2_opt_a = QuestionOption.objects.create(question=self.q2, text="No", is_correct=True)
        self.q2_opt_b = QuestionOption.objects.create(question=self.q2, text="Yes", is_correct=False)

        # 4. Setup Exam
        self.exam = Exam.objects.create(
            name="Unit Test 1",
            course=self.course,
            duration_minutes=60,
            start_datetime=timezone.now() - timedelta(minutes=10),
            end_datetime=timezone.now() + timedelta(minutes=50),
            status=Exam.Status.RUNNING,
            created_by=self.teacher
        )
        # Add questions to exam
        self.exam.questions.add(self.q1, through_defaults={'order': 1})
        self.exam.questions.add(self.q2, through_defaults={'order': 2})

    def test_student_exam_flow(self):
        """
        Simulates the full flow: Start Exam -> Answer Questions -> Submit -> Check Score
        """
        client = self.client
        
        # 1. Login as Student
        login_success = client.login(username='student_flow', password='password')
        self.assertTrue(login_success)

        # 2. Start Exam
        response = client.post(f'/api/exams/start/{self.exam.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        attempt_id = data['attempt_id']
        self.assertIsNotNone(attempt_id)
        
        # Verify attempt created in DB
        attempt = ExamStudent.objects.get(id=attempt_id)
        self.assertEqual(attempt.status, ExamStudent.Status.IN_PROGRESS)

        # 3. Submit Answer for Q1 (Correct)
        response = client.post('/api/exams/save-answer/', {
            'attempt_id': attempt_id,
            'question_id': self.q1.id,
            'selected_options': [self.q1_opt_b.id] # Correct
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 4. Submit Answer for Q2 (Incorrect)
        response = client.post('/api/exams/save-answer/', {
            'attempt_id': attempt_id,
            'question_id': self.q2.id,
            'selected_options': [self.q2_opt_b.id] # Wrong
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 5. Submit Exam
        response = client.post(f'/api/exams/submit/{attempt_id}/')
        self.assertEqual(response.status_code, 200)
        
        # 6. Verify Results
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, ExamStudent.Status.SUBMITTED)
        
        # Expected Score: Q1 (1 mark) + Q2 (0 marks) = 1.0
        # Total possible was 3.
        self.assertEqual(attempt.score_objective, 1.0)
        print(f"\nTest Result: Student scored {attempt.score_objective}/{self.exam.questions.aggregate(total=models.Sum('marks'))['total'] or 3} correctly.")
