from django import forms
from .models import Order, Client
from accounts.models import User
from logistics.models import Vehicle


class OrderEditForm(forms.ModelForm):
    """Form for dispatchers to edit order driver and status"""
    
    class Meta:
        model = Order
        fields = ['driver', 'vehicle', 'status']
        widgets = {
            'driver': forms.Select(attrs={'class': 'form-input'}),
            'vehicle': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }
        labels = {
            'driver': 'Assigned Driver',
            'vehicle': 'Assigned Vehicle',
            'status': 'Order Status',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter drivers


class OrderForm(forms.ModelForm):
    """Form for creating and editing Orders"""
    
    class Meta:
        model = Order
        fields = [
            'client',
            'cargo_type',
            'cargo_mass_kg',
            'origin',
            'destination',
            'driver',
            'vehicle',
            'status',
            'pickup_datetime',
            'delivery_datetime',
            'agreed_price',
        ]
        widgets = {
            'cargo_type': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Medical Supplies - Temperature Controlled'
            }),
            'cargo_mass_kg': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Weight in kg'
            }),
            'origin': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Moscow'
            }),
            'destination': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., St. Petersburg'
            }),
            'driver': forms.Select(attrs={
                'class': 'form-input'
            }),
            'vehicle': forms.Select(attrs={
                'class': 'form-input'
            }),
            'client': forms.Select(attrs={
                'class': 'form-input'
            }),
            'status': forms.Select(attrs={
                'class': 'form-input'
            }),
            'pickup_datetime': forms.DateTimeInput(attrs={
                'class': 'form-input',
                'type': 'datetime-local'
            }),
            'delivery_datetime': forms.DateTimeInput(attrs={
                'class': 'form-input',
                'type': 'datetime-local'
            }),
            'agreed_price': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., 15000.00'
            }),
        }
        labels = {
            'cargo_type': 'Cargo Description',
            'cargo_mass_kg': 'Cargo Weight (kg)',
            'origin': 'Origin',
            'destination': 'Destination',
            'driver': 'Assigned Driver (Optional)',
            'vehicle': 'Assigned Vehicle (Optional)',
            'client': 'Client',
            'status': 'Initial Status',
            'pickup_datetime': 'Pickup Date & Time',
            'delivery_datetime': 'Delivery Date & Time',
            'agreed_price': 'Agreed Price',
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter drivers to only show users with role='driver'
        self.fields['driver'].queryset = User.objects.filter(role='driver')
        self.fields['driver'].required = False
        
        # Make vehicle optional
        self.fields['vehicle'].required = False
        self.fields['agreed_price'].required = False
        
        # Filter clients by user's company if user is provided
        if user and user.company:
            self.fields['client'].queryset = Client.objects.filter(company=user.company)


"""
class OrderEditForm(forms.ModelForm):
    
    class Meta:
        model = Order 
        fields = ['driver', 'vehicle', 'status']
        widgets = {
            'driver': forms.Select(attrs={'class': 'form-input'}),
            'vehicle': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }
        labels = {
            'driver': 'Assigned Driver',
            'vehicle': 'Assigned Vehicle',
            'status': 'Order Status',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter drivers
        self.fields['driver'].queryset = User.objects.filter(role='driver')
        self.fields['driver'].required = False
        self.fields['vehicle'].required = False
"""

class DriverOrderStatusForm(forms.ModelForm):
    """Form for drivers to update order status"""
    
    class Meta:
        model = Order
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'status': 'Order Status',
        }


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ['reg_number', 'type', 'model', 'capacity_kg', 'last_maintenance', 'status']
        widgets = {
            'reg_number': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.TextInput(attrs={'class': 'form-control'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity_kg': forms.NumberInput(attrs={'class': 'form-control'}),
            'last_maintenance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'status': 'Vehicle Status', # Corrected label for clarity
        }
