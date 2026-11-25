"""
PHASE 5 PART 4 - the two tables behind login protection.

  LoginFailure   one row per wrong password (kept one day, then cleaned up)
  RevokedToken   a token that was signed out; refused until it would have
                 expired anyway, then cleaned up
"""
from django.db import models
from django.utils import timezone


class LoginFailure(models.Model):
    username = models.CharField(max_length=150, db_index=True)   # lower-case
    ip = models.CharField(max_length=64, blank=True, db_index=True)
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.username} from {self.ip} at {self.at:%Y-%m-%d %H:%M}"


class RevokedToken(models.Model):
    jti = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)

    def __str__(self):
        return self.jti
