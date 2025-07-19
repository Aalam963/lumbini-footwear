from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_socketio import SocketIO, emit, join_room
from extensions import db
from models import User, Attendance, Credit, InboxMessage
import random
import string
from datetime import datetime, time, date
import os

# Debug info to check templates folder
print("Starting Flask app...")
print("Current working directory:", os.getcwd())
print("Templates folder exists?", os.path.isdir('templates'))
print("Templates contents:", os.listdir('templates') if os.path.isdir('templates') else "No folder")

# Create Flask app and explicitly set templates folder path
app = Flask(__name__, template_folder=os.path.abspath('templates'))

app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lumbini_footwear.db'

db.init_app(app)
socketio = SocketIO(app, manage_session=False)  # We manage sessions manually

with app.app_context():
    db.create_all()

    # Create default owner if not exists
    owner = User.query.filter_by(username='owner').first()
    if not owner:
        owner = User(username='owner', role='owner')
        owner.password = 'ownerpass'  # Make sure hashing is in your User model setter
        db.session.add(owner)
        db.session.commit()
        print("Default owner created: username='owner' password='ownerpass'")

def generate_password(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def add_inbox_message(text, user_id=None):
    msg = InboxMessage(content=text, user_id=user_id)
    db.session.add(msg)
    db.session.commit()
    socketio.emit('new_inbox_message', {'message': text}, room='owner')

# -------- ROUTES -----------

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            if user.role == 'owner':
                return redirect(url_for('owner_dashboard'))
            else:
                return redirect(url_for('staff_dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# ------ OWNER DASHBOARD ------

@app.route('/owner/dashboard')
def owner_dashboard():
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    staffs = User.query.filter_by(role='staff').all()
    return render_template('owner_dashboard.html', username=session.get('username'), staffs=staffs)

@app.route('/owner/add_staff', methods=['POST'])
def add_staff():
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    staff_username = request.form['staff_username']
    if User.query.filter_by(username=staff_username).first():
        flash('Staff already exists.', 'danger')
        return redirect(url_for('owner_dashboard'))
    new_pass = generate_password()
    new_staff = User(username=staff_username, role='staff')
    new_staff.password = new_pass
    db.session.add(new_staff)
    db.session.commit()
    flash(f"Staff '{staff_username}' added. Password: {new_pass}", 'success')
    add_inbox_message(f"Staff '{staff_username}' added successfully with password: {new_pass}")
    return redirect(url_for('owner_dashboard'))

@app.route('/owner/remove_staff/<int:staff_id>')
def remove_staff(staff_id):
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    staff = User.query.get(staff_id)
    if staff and staff.role == 'staff':
        db.session.delete(staff)
        db.session.commit()
        flash(f"Staff '{staff.username}' removed.", 'success')
    else:
        flash('Staff not found.', 'danger')
    return redirect(url_for('owner_dashboard'))

# ------ STAFF DASHBOARD ------

@app.route('/staff/dashboard')
def staff_dashboard():
    if session.get('role') != 'staff':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    return render_template('staff_dashboard.html', username=session.get('username'))

@app.route('/staff/inbox')
def staff_inbox():
    if session.get('role') != 'staff':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    inbox_messages = InboxMessage.query.filter_by(user_id=user_id).order_by(InboxMessage.timestamp.desc()).all()
    return render_template('staff_inbox.html', inbox=inbox_messages)

@app.route('/staff/checkin')
def staff_checkin():
    if session.get('role') != 'staff':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    user_id = session['user_id']
    now = datetime.now()
    late = now.time() > time(8, 0)  # Late if after 8 AM
    attendance = Attendance(user_id=user_id, checkin_time=now, late=late)
    db.session.add(attendance)
    db.session.commit()
    if late:
        socketio.emit('late_warning', {'time': now.strftime('%H:%M:%S')}, room=f'staff_{user_id}')
        user = User.query.get(user_id)
        add_inbox_message(f"Staff '{user.username}' checked in late today at {now.strftime('%H:%M:%S')}", user_id=user.id)
    flash("Checked in successfully.", "success")
    return redirect(url_for('staff_dashboard'))

# ------ SALARY MANAGEMENT ------

@app.route('/owner/salary/<int:staff_id>', methods=['GET', 'POST'])
def manage_salary(staff_id):
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    staff = User.query.get(staff_id)
    if not staff or staff.role != 'staff':
        flash('Staff not found.', 'danger')
        return redirect(url_for('owner_dashboard'))
    if request.method == 'POST':
        salary = request.form.get('salary', type=int)
        credit_taken = request.form.get('credit_taken', type=float)
        if salary is not None:
            staff.salary = salary
        if credit_taken is not None:
            staff.credit_taken = (staff.credit_taken or 0) + credit_taken
        db.session.commit()
        flash(f"Salary and credit updated for {staff.username}", "success")
        return redirect(url_for('owner_dashboard'))
    return render_template('manage_salary.html', staff=staff)

# ------ CREDIT MANAGEMENT ------

@app.route('/owner/credit/<int:staff_id>', methods=['GET', 'POST'])
def manage_credit(staff_id):
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    staff = User.query.get(staff_id)
    if not staff or staff.role != 'staff':
        flash('Staff not found.', 'danger')
        return redirect(url_for('owner_dashboard'))
    if request.method == 'POST':
        amount = request.form.get('amount', type=float)
        date_str = request.form.get('date_taken')
        if not amount or amount <= 0:
            flash('Please enter a valid credit amount.', 'danger')
            return redirect(url_for('manage_credit', staff_id=staff_id))
        try:
            credit_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'danger')
            return redirect(url_for('manage_credit', staff_id=staff_id))
        new_credit = Credit(amount=amount, date_taken=credit_date, user_id=staff.id)
        db.session.add(new_credit)
        staff.credit_taken = (staff.credit_taken or 0) + amount
        db.session.commit()
        add_inbox_message(f"Credit of {amount} added for Staff '{staff.username}' on {credit_date.strftime('%Y-%m-%d')}", user_id=staff.id)
        flash(f"Added credit of {amount} on {credit_date} for {staff.username}", "success")
        return redirect(url_for('manage_credit', staff_id=staff_id))
    credits = Credit.query.filter_by(user_id=staff.id).order_by(Credit.date_taken.desc()).all()
    return render_template('manage_credit.html', staff=staff, credits=credits)

# ------ OWNER INBOX ------

@app.route('/owner/inbox')
def owner_inbox():
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    inbox_messages = InboxMessage.query.order_by(InboxMessage.timestamp.desc()).all()
    return render_template('owner_inbox.html', inbox=inbox_messages)

# ------ CHAT SYSTEM ------

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session.get('username'), role=session.get('role'))

@socketio.on('join')
def on_join(data):
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or not role:
        return
    join_room(f"{role}_{user_id}")
    if role == 'owner':
        join_room('owner')
    elif role == 'staff':
        join_room('staff')
    print(f"{session.get('username')} joined room: {role}_{user_id}")

@socketio.on('send_message')
def handle_send_message(data):
    sender = session.get('username')
    role = session.get('role')
    msg = data.get('message')
    if not msg or not sender or not role:
        return
    emit('receive_message', {'sender': sender, 'role': role, 'message': msg}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
