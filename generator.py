import os
import time
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, field_validator, Field
from typing import List

load_dotenv()

class MCQQuestion(BaseModel):
    question: str = Field(description="The question text")
    options: List[str] = Field(description="List of 4 possible answers")
    correct_answer: str = Field(description="The correct answer from the options")

    @field_validator("question", mode="before")
    @classmethod
    def clean_question(cls, v):
        if isinstance(v, dict):
            return v.get('description', str(v))
        return str(v)

class QuestionGenerator:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            model="gemini-1.5-flash",
            temperature=0.7,  # Reduced for more consistent results
            max_tokens=500,   # Limit token usage
            timeout=30        # Add timeout to prevent hanging
        )
        self.last_call_time = 0
        self.min_call_interval = 1.0  # Minimum 1 second between API calls
    
    def _rate_limit(self):
        """Ensure we don't overwhelm the API"""
        current_time = time.time()
        time_since_last = current_time - self.last_call_time
        if time_since_last < self.min_call_interval:
            time.sleep(self.min_call_interval - time_since_last)
        self.last_call_time = time.time()
    
    def generate_mcq(self, topic: str, difficulty: str = 'medium') -> MCQQuestion:
        """Generate MCQ with optimized prompting and reduced retries"""
        self._rate_limit()
        
        mcq_parser = PydanticOutputParser(pydantic_object=MCQQuestion)

        # More specific and efficient prompt
        prompt = PromptTemplate(
            template=(
                "Create a {difficulty} level multiple choice question about {topic}.\n"
                "Requirements:\n"
                "- Question must be clear and specific\n"
                "- Provide exactly 4 options\n"
                "- One correct answer\n"
                "- Three plausible wrong answers\n\n"
                "Format your response as valid JSON:\n"
                '{{\n'
                '  "question": "Your question here?",\n'
                '  "options": ["Option A", "Option B", "Option C", "Option D"],\n'
                '  "correct_answer": "Option A"\n'
                '}}\n\n'
                "Topic: {topic}\n"
                "Difficulty: {difficulty}\n"
                "Response:"
            ),
            input_variables=['topic', 'difficulty']
        )

        # Reduced retry attempts to save API quota
        max_attempts = 2  # Reduced from 3
        for attempt in range(max_attempts):
            try:
                response = self.llm.invoke(prompt.format(topic=topic, difficulty=difficulty))
                
                # Clean the response content
                content = response.content.strip()
                if content.startswith("```json"):
                    content = content[7:-3]
                elif content.startswith("```"):
                    content = content[3:-3]
                
                parsed_response = mcq_parser.parse(content)
                
                # Validate the response
                if (not parsed_response.question or 
                    len(parsed_response.options) != 4 or 
                    not parsed_response.correct_answer or
                    parsed_response.correct_answer not in parsed_response.options):
                    raise ValueError('Invalid question format')
                
                return parsed_response
                
            except Exception as e:
                if attempt == max_attempts - 1:
                    # Create a fallback question instead of failing
                    return self._create_fallback_mcq(topic, difficulty)
                continue

    def _create_fallback_mcq(self, topic: str, difficulty: str) -> MCQQuestion:
        """Create a simple fallback MCQ when API fails"""
        return MCQQuestion(
            question=f"What is a key concept related to {topic}?",
            options=[
                f"Basic concept of {topic}",
                "Unrelated concept A",
                "Unrelated concept B", 
                "Unrelated concept C"
            ],
            correct_answer=f"Basic concept of {topic}"
        )