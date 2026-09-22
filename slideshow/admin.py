from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, Mosque, PrayerTime, MosqueSlide


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Plan & Vertical'
    fields = ('vertical', 'number_of_screens', 'max_slideshows', 'storage_quota_mb')


class MosqueInline(admin.StackedInline):
    model = Mosque
    extra = 1
    verbose_name_plural = 'Mosque Details'
    fields = ('name', 'address', 'latitude', 'longitude', 'is_active')


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, MosqueInline)


if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(UserProfile)


class PrayerTimeInline(admin.TabularInline):
    model = PrayerTime
    extra = 1


@admin.register(Mosque)
class MosqueAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'address')
    inlines = [PrayerTimeInline]


@admin.register(PrayerTime)
class PrayerTimeAdmin(admin.ModelAdmin):
    list_display = ('mosque', 'date', 'fajr', 'dhuhr', 'asr', 'maghrib', 'isha', 'jummah', 'jummah2', 'jummah3')
    list_filter = ('mosque', 'date')
    date_hierarchy = 'date'


@admin.register(MosqueSlide)
class MosqueSlideAdmin(admin.ModelAdmin):
    list_display = ('title', 'mosque', 'order', 'is_active', 'created_at')
    list_filter = ('mosque', 'is_active')
    search_fields = ('title',)
