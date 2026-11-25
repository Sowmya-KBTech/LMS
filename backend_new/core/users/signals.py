# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django.contrib.auth import get_user_model

# from courses.models import (
#     TeachingAssignment,
#     Enrollment
# )

# User = get_user_model()


# @receiver(post_save, sender=User)
# def auto_enroll_student(
#     sender,
#     instance,
#     created,
#     **kwargs
# ):

#     # ================= ONLY NEW STUDENTS =================
#     if not created:
#         return

#     if instance.role != "student":
#         return

#     # ================= REQUIRED FIELDS =================
#     if (
#         not instance.course
#         or not instance.year
#         or not instance.semester
#     ):
#         return

#     # ================= FIND MATCHING TEACHING ASSIGNMENTS =================
#     teaching_assignments = TeachingAssignment.objects.filter(

#         # MATCH COURSE
#         course=instance.course,

#         # MATCH YEAR
#         year__year_number=
#         instance.year,

#         # MATCH SEMESTER
#         subject__semester=
#         instance.semester
#     )

#     # ================= CREATE ENROLLMENTS =================
#     enrollments = []

#     for assignment in teaching_assignments:

#         exists = Enrollment.objects.filter(
#             student=instance,
#             teaching_assignment=assignment
#         ).exists()

#         if not exists:

#             enrollments.append(

#                 Enrollment(
#                     student=instance,
#                     teaching_assignment=assignment
#                 )
#             )

#     # ================= BULK CREATE =================
#     Enrollment.objects.bulk_create(
#         enrollments
#     )