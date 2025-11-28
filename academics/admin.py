from django.contrib import admin
from .models import Department, Course, CourseEnrollment

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'semester')
    list_filter = ('department', 'semester')
    search_fields = ('name', 'code')

@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'section', 'enrolled_at')
    list_filter = ('course', 'section')
    search_fields = ('student__username', 'course__code')
