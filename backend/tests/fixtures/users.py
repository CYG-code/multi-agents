from app.models.user import UserRole

USERS = {
    "student": {
        "username": "student_1",
        "password": "password123",
        "display_name": "Student 1",
        "role": UserRole.student,
    },
    "teacher": {
        "username": "teacher_1",
        "password": "password123",
        "display_name": "Teacher 1",
        "role": UserRole.teacher,
    },
}

