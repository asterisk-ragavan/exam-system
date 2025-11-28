from django.shortcuts import redirect, render

def index(request):
    if request.user.is_authenticated:
        if request.user.role == 'TEACHER' or request.user.role == 'ADMIN':
            return redirect('teacher_dashboard')
        elif request.user.role == 'STUDENT':
            return redirect('student_dashboard')
    return redirect('/admin/login/')
