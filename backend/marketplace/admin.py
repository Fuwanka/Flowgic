from django.contrib import admin

from .models import OfferClickLog, PartnerOffer


@admin.register(PartnerOffer)
class PartnerOfferAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'company', 'active', 'is_demo', 'priority']
    list_filter = ['category', 'active', 'is_demo']
    search_fields = ['title', 'slug', 'company__name']
    list_select_related = ['company']


@admin.register(OfferClickLog)
class OfferClickLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'company', 'offer', 'user', 'order']
    list_filter = ['offer__category']
    list_select_related = ['company', 'offer', 'user', 'order']
    readonly_fields = ['id', 'created_at', 'company', 'offer', 'user', 'order']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
