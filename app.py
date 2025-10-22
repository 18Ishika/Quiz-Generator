from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets
import os
import re
from dotenv import load_dotenv
from generator import QuestionGenerator

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
        
        try:
            generator = QuestionGenerator()
            questions = []
            
            for _ in range(num_questions):
                q = generator.generate_mcq(topic, difficulty.lower())
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
    
    return render_template('take_quiz.html', quiz=quiz)

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
