from django import forms
from logistics.models import Client


class ClientForm(forms.ModelForm):
    """Form for creating and editing Clients"""
    
    class Meta:
        model = Client
        fields = ['name', 'phone', 'email']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Acme Corporation'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., +7 (999) 123-45-67'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., contact@example.com'
            }),
        }
        labels = {
            'name': 'Client Name',
            'phone': 'Phone Number (Optional)',
            'email': 'Email Address (Optional)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make phone and email optional
        self.fields['phone'].required = False
        self.fields['email'].required = False
