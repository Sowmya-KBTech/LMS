from django.contrib import admin
from .models import InternalAssessment, IAMark, SemesterResult, ResultEntry,ExamSchedule

@admin.register(InternalAssessment)
class InternalAssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "teaching_assignment", "number", "max_marks", "is_locked")
    list_filter = ("number", "is_locked")


@admin.register(IAMark)
class IAMarkAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment", "student", "marks_obtained", "is_absent")
    list_filter = ("is_absent",)

@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "semester", "exam_date", "session")
    list_filter = ("semester", "session")


# show subject entries inline inside the semester result page
class ResultEntryInline(admin.TabularInline):
    model = ResultEntry
    extra = 0
    readonly_fields = ("grade", "is_pass")


@admin.register(SemesterResult)
class SemesterResultAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "semester", "is_published", "created_at")
    list_filter = ("semester", "is_published")
    search_fields = ("student__username", "student__roll_number")
    inlines = [ResultEntryInline]


@admin.register(ResultEntry)
class ResultEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "result", "subject", "marks_obtained", "max_marks", "grade", "is_pass")
    list_filter = ("is_pass",)
    readonly_fields = ("grade", "is_pass")