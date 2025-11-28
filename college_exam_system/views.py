from django.shortcuts import redirect, render

def index(request):
    if request.user.is_authenticated:
        if request.user.role == 'TEACHER' or request.user.role == 'ADMIN':
            return redirect('teacher-dashboard')
        elif request.user.role == 'STUDENT':
            return redirect('student-dashboard')
    return redirect('/admin/login/')
