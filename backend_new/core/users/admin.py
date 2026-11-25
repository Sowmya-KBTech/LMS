# Register your models here.
from django.contrib import admin
from .models import User
from .models import ParentProfile

admin.site.register(User)

@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ['user','get_children']
    filter_horizontal = ['children']
    def get_children(self, obj):
        return ", ".join(c.username for c in obj.children.all())
    get_children.short_description = 'Children'
    