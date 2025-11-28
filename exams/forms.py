from django import forms
from academics.models import Course

class QuestionImportForm(forms.Form):
    course = forms.ModelChoiceField(
        queryset=Course.objects.all(), 
        label="Select Course",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    csv_file = forms.FileField(
        label="Upload CSV File", 
        help_text="Format: Question Text, Difficulty (E/M/H), Marks, Option1, IsCorrect1, Option2, IsCorrect2, ...",
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
