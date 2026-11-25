from django.apps import AppConfig


class CoursesConfig(AppConfig):
    """
    Academics: Course, Year, Subject, TeachingAssignment, Enrollment, YearTutor.

    The app label stays 'courses' on purpose: the database tables
    (courses_course, courses_subject, ...) and every migration that other
    apps depend on use that name. Renaming the label would mean rewriting
    the whole migration history.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core.academics'
    label = 'courses'
    verbose_name = 'Academics'
