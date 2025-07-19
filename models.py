from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

class User(db.Model):
    __tablename__ = 'user'  # Explicit table name to match foreign keys
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'owner' or 'staff'
    salary = db.Column(db.Integer, default=0)
    credit_taken = db.Column(db.Float, default=0.0)  # total credit taken by staff

    @property
    def password(self):
        raise AttributeError("Password is not readable.")

    @password.setter
    def password(self, plaintext):
        self.password_hash = generate_password_hash(plaintext)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    checkin_time = db.Column(db.DateTime, default=datetime.utcnow)
    checkout_time = db.Column(db.DateTime, nullable=True)
    late = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref=db.backref('attendances', cascade='all, delete-orphan'))

class Credit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    date_taken = db.Column(db.Date, default=date.today)  # Use date.today for a Date column
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)

    user = db.relationship('User', backref=db.backref('credits', cascade='all, delete-orphan'))

# NEW MODEL: For storing inbox messages
class InboxMessage(db.Model):
    __tablename__ = 'inbox_messages'
    __table_args__ = {'extend_existing': True}  # Avoids redefinition errors

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(255), nullable=False)  # Message content here
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)

    user = db.relationship('User', backref=db.backref('inbox_messages', cascade='all, delete-orphan'))
