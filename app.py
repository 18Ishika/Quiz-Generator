from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets
import os
import re
from dotenv import load_dotenv
from generator import QuestionGenerator
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO

load_dotenv()

# Debug: Print to verify env variables are loaded
print("Environment variables loaded:")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')[:50]}..." if os.getenv('DATABASE_URL') else "DATABASE_URL: Not set")
print(f"SECRET_KEY: {'Set' if os.getenv('SECRET_KEY') else 'Not set'}")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(16))

# PostgreSQL Configuration
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    quizzes = db.relationship('Quiz', backref='creator', lazy=True, cascade='all, delete-orphan')

class Quiz(db.Model):
    __tablename__ = 'quiz'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    topic = db.Column(db.String(100), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    share_link = db.Column(db.String(50), unique=True, nullable=False)
    questions = db.Column(db.JSON, nullable=False)
    shuffle_options = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy=True, cascade='all, delete-orphan')

class QuizAttempt(db.Model):
    __tablename__ = 'quiz_attempt'
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    student_name = db.Column(db.String(100), nullable=False)
    student_email = db.Column(db.String(100))
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    answers = db.Column(db.JSON, nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Initialize database
with app.app_context():
    db.create_all()

def normalize_answer(answer):
    """Normalize answer for comparison"""
    if not answer:
        return ''
    answer = str(answer).strip().lower()
    answer = re.sub(r'\s+', ' ', answer)
    return answer

def create_pdf_report(quiz, attempts):
    """Create a PDF report for a quiz"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a5490'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    elements.append(Paragraph("Quiz Report", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Quiz Information Table
    quiz_info_data = [
        ['Quiz Title:', quiz.title],
        ['Topic:', quiz.topic],
        ['Difficulty:', quiz.difficulty.capitalize()],
        ['Total Questions:', str(len(quiz.questions))],
        ['Created:', quiz.created_at.strftime("%B %d, %Y at %H:%M")],
    ]
    
    quiz_info_table = Table(quiz_info_data, colWidths=[2*inch, 4.5*inch])
    quiz_info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f0f7')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ccc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    elements.append(quiz_info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Statistics
    total_attempts = len(attempts)
    if total_attempts > 0:
        avg_score = sum(a.score for a in attempts) / total_attempts
        avg_percentage = (avg_score / len(quiz.questions)) * 100
    else:
        avg_score = 0
        avg_percentage = 0
    
    elements.append(Paragraph("Statistics Overview", heading_style))
    
    stats_data = [
        ['Total Attempts', 'Average Score', 'Average Percentage'],
        [str(total_attempts), f"{avg_score:.2f} / {len(quiz.questions)}", f"{avg_percentage:.1f}%"]
    ]
    
    stats_table = Table(stats_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 14),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f5fa')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ccc')),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    
    elements.append(stats_table)
    elements.append(Spacer(1, 0.4*inch))
    
    # Student Results
    if attempts:
        elements.append(Paragraph("Student Results", heading_style))
        
        # Table header
        results_data = [['#', 'Student Name', 'Email', 'Score', 'Percentage', 'Date & Time']]
        
        # Add student data
        for idx, attempt in enumerate(attempts, 1):
            percentage = (attempt.score / attempt.total_questions) * 100
            results_data.append([
                str(idx),
                attempt.student_name,
                attempt.student_email or 'N/A',
                f"{attempt.score}/{attempt.total_questions}",
                f"{percentage:.1f}%",
                attempt.completed_at.strftime("%m/%d/%Y %H:%M")
            ])
        
        results_table = Table(results_data, colWidths=[0.4*inch, 1.8*inch, 1.8*inch, 0.9*inch, 1*inch, 1.3*inch])
        
        # Create table style
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]
        
        # Alternate row colors
        for i in range(1, len(results_data)):
            if i % 2 == 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f9f9f9')))
            else:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.white))
            
            # Color code percentages
            percentage = (attempts[i-1].score / attempts[i-1].total_questions) * 100
            if percentage >= 80:
                table_style.append(('TEXTCOLOR', (4, i), (4, i), colors.HexColor('#28a745')))
                table_style.append(('FONTNAME', (4, i), (4, i), 'Helvetica-Bold'))
            elif percentage >= 60:
                table_style.append(('TEXTCOLOR', (4, i), (4, i), colors.HexColor('#007bff')))
                table_style.append(('FONTNAME', (4, i), (4, i), 'Helvetica-Bold'))
            elif percentage >= 40:
                table_style.append(('TEXTCOLOR', (4, i), (4, i), colors.HexColor('#ffc107')))
                table_style.append(('FONTNAME', (4, i), (4, i), 'Helvetica-Bold'))
            else:
                table_style.append(('TEXTCOLOR', (4, i), (4, i), colors.HexColor('#dc3545')))
                table_style.append(('FONTNAME', (4, i), (4, i), 'Helvetica-Bold'))
        
        results_table.setStyle(TableStyle(table_style))
        elements.append(results_table)
    else:
        elements.append(Paragraph("No attempts yet.", styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

# Auth Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Username already exists')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already registered')
        
        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            name=name
        )
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.password and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Main Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create-quiz', methods=['GET', 'POST'])
@login_required
def create_quiz():
    if request.method == 'POST':
        topic = request.form.get('topic')
        difficulty = request.form.get('difficulty', 'medium')
        num_questions = int(request.form.get('num_questions', 5))
        title = request.form.get('title', f"{topic} Quiz")
        shuffle_options = request.form.get('shuffle_options') == 'on'
        
        try:
            generator = QuestionGenerator()
            questions = []
            
            for _ in range(num_questions):
                q = generator.generate_mcq(topic, difficulty.lower(), shuffle_options=shuffle_options)
                questions.append({
                    'question': q.question,
                    'options': q.options,
                    'correct_answer': q.correct_answer
                })
            
            share_link = secrets.token_urlsafe(8)
            
            quiz = Quiz(
                user_id=current_user.id,
                title=title,
                topic=topic,
                difficulty=difficulty,
                share_link=share_link,
                questions=questions
            )
            
            # Set shuffle_options if column exists
            try:
                quiz.shuffle_options = shuffle_options
            except:
                pass  # Column doesn't exist yet, skip it
            
            db.session.add(quiz)
            db.session.commit()
            
            return redirect(url_for('quiz_created', share_link=share_link))
        
        except Exception as e:
            return render_template('create_quiz.html', error=str(e))
    
    return render_template('create_quiz.html')

@app.route('/quiz-created/<share_link>')
@login_required
def quiz_created(share_link):
    quiz = Quiz.query.filter_by(share_link=share_link).first_or_404()
    if quiz.user_id != current_user.id:
        return redirect(url_for('index'))
    quiz_url = request.host_url + 'quiz/' + share_link
    return render_template('quiz_created.html', quiz=quiz, quiz_url=quiz_url)

@app.route('/quiz/<share_link>', methods=['GET', 'POST'])
def take_quiz(share_link):
    quiz = Quiz.query.filter_by(share_link=share_link).first_or_404()
    
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        student_email = request.form.get('student_email', '')
        
        score = 0
        answers = []
        
        for i, question in enumerate(quiz.questions):
            user_answer = request.form.get(f'question_{i}')
            correct_answer = question['correct_answer']
            
            user_normalized = normalize_answer(user_answer)
            correct_normalized = normalize_answer(correct_answer)
            
            is_correct = user_normalized == correct_normalized
            
            if is_correct:
                score += 1
            
            answers.append({
                'question': question['question'],
                'user_answer': user_answer,
                'correct_answer': correct_answer,
                'is_correct': is_correct
            })
        
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            student_name=student_name,
            student_email=student_email,
            score=score,
            total_questions=len(quiz.questions),
            answers=answers
        )
        db.session.add(attempt)
        db.session.commit()
        
        return redirect(url_for('quiz_results', attempt_id=attempt.id))
    
    # Shuffle options if enabled (for display only)
    display_questions = []
    import random
    for question in quiz.questions:
        q_copy = question.copy()
        if quiz.shuffle_options:
            # Create a copy and shuffle the options
            options_copy = q_copy['options'].copy()
            random.shuffle(options_copy)
            q_copy['options'] = options_copy
        display_questions.append(q_copy)
    
    return render_template('take_quiz.html', quiz=quiz, questions=display_questions)

@app.route('/results/<int:attempt_id>')
def quiz_results(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    percentage = (attempt.score / attempt.total_questions) * 100
    return render_template('results.html', attempt=attempt, percentage=percentage)

@app.route('/my-quizzes')
@login_required
def my_quizzes():
    quizzes = Quiz.query.filter_by(user_id=current_user.id).order_by(Quiz.created_at.desc()).all()
    return render_template('my_quizzes.html', quizzes=quizzes)

@app.route('/quiz-report/<share_link>')
@login_required
def quiz_report(share_link):
    quiz = Quiz.query.filter_by(share_link=share_link).first_or_404()
    if quiz.user_id != current_user.id:
        return redirect(url_for('index'))
    
    attempts = QuizAttempt.query.filter_by(quiz_id=quiz.id).order_by(QuizAttempt.completed_at.desc()).all()
    
    total_attempts = len(attempts)
    if total_attempts > 0:
        avg_score = sum(a.score for a in attempts) / total_attempts
        avg_percentage = (avg_score / len(quiz.questions)) * 100
    else:
        avg_score = 0
        avg_percentage = 0
    
    return render_template('quiz_report.html', 
                         quiz=quiz, 
                         attempts=attempts, 
                         total_attempts=total_attempts,
                         avg_percentage=avg_percentage)

@app.route('/download-report/<share_link>')
@login_required
def download_report(share_link):
    quiz = Quiz.query.filter_by(share_link=share_link).first_or_404()
    if quiz.user_id != current_user.id:
        return redirect(url_for('index'))
    
    attempts = QuizAttempt.query.filter_by(quiz_id=quiz.id).order_by(QuizAttempt.completed_at.desc()).all()
    
    # Generate PDF file
    pdf_file = create_pdf_report(quiz, attempts)
    
    # Create filename
    filename = f"{quiz.title.replace(' ', '_')}_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return send_file(
        pdf_file,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@app.route('/delete-quiz/<int:quiz_id>', methods=['POST'])
@login_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.user_id != current_user.id:
        return redirect(url_for('index'))
    db.session.delete(quiz)
    db.session.commit()
    return redirect(url_for('my_quizzes'))

import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )