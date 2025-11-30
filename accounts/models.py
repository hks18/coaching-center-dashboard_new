
from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("centerowner", "Center Owner"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    center = models.CharField(max_length=100)  # FREE TEXT, NO CHOICES


    def __str__(self):
        return f"{self.user.username} - {self.role} - {self.center}"


class DailyCustomer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.name}"
