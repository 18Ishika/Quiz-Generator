import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel , field_validator ,Field
from typing import List

load_dotenv()

class MCQQuestion(BaseModel):
    question: str =Field(description="The question text")
    options: List[str]=Field(description="List of 4 possible answers")
    correct_answer: str=Field(description="The correct answer from the options")

    @field_validator("question",pre=True)
    @classmethod
    def clean_question(cls,v): #clean the question
        if isinstance(v,dict):
            return v.get('description',str(v))  #{description:"what is capital of india"} ->> "what---india"
        return str(v)

class FillInTheBlank(BaseModel):
    question: str=Field(description="The question text with '______' for the blank")
    answer: str=Field(description="The correct answer or word for the blank")
    @field_validator("question",pre=True)
    @classmethod
    def clean_question(cls,v):
        if isinstance(v,dict):
            return v.get('description',str(v))
        return str(v)

class QuestionGenerator:
    def __init__(self):
        """
        Initialise question generator with Google API
        """
        self.llm=ChatGoogleGenerativeAI(
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            model="gemini-1.5-flash",
            temperature=0.7
        )
    def generate_mcq(self, topic: str, difficulty: str = 'medium') -> MCQQuestion:
        mcq_parser = PydanticOutputParser(pydantic_object=MCQQuestion)

        prompt = PromptTemplate(
            template=(
                "Generate a {difficulty} multiple choice question about {topic}. \n\n"
                "Return only a JSON object with exact these fields:\n"
                " - 'question':A clear and specific question\n"
                "- 'options' :An array of exactly four possible answers\n"
                "- 'correct_answer' :One of the options that is the correct answer.\n\n"
                "Example format: \n"
                '{{\n'
                ' "question": "What is capital of France?",\n'
                ' "options": ["London","Berlin","Paris","Madrid"],\n'
                ' "correct_answer": "Paris"\n'
                '}}\n\n'
                "Your Response:"
            ),
            input_variables=['topic','difficulty']
        )

        max_attempts=3
        for attempt in range(max_attempts):
            try:
                response=self.llm.invoke(prompt.format(topic=topic,difficulty=difficulty))
                parsed_response=mcq_parser.parse(response.content)
                if not parsed_response.question or len(parsed_response.options)!=4 or not parsed_response.correct_answer:
                    raise ValueError('Invalid question format')
                if parsed_response.correct_answer not in parsed_response.options:
                    raise ValueError("Correct answer not in options")
                return parsed_response
            except Exception as e:
                if attempt==max_attempts-1:
                    raise RuntimeError(f"Failed to generate valid MCQ after {max_attempts} attempts :{str(e)}")
                continue

        
    def generate_fill_blank(self, topic: str, difficulty: str = 'medium') -> FillInTheBlank:
        fill_in_blank_parser = PydanticOutputParser(pydantic_object=FillInTheBlank)

        prompt = PromptTemplate(
            template=(
                "Generate a {difficulty} fill-in-the-blank about {topic}. \n\n"
                "Return only a JSON object with exact these fields:\n"
                " - 'question':A sentence with '______' marking where blank should be\n"
                "- 'answer' : The correct word or phrase that belongs to the blank.\n\n"
                "Example format: \n"
                '{{\n'
                ' "question": "The capital of France is ______.",\n'
                ' "answer": "Paris"\n'
                '}}\n\n'
                "Your Response:"
            ),
            input_variables=['topic','difficulty']
        )

        max_attempts=3
        for attempt in range(max_attempts):
            try:
                response=self.llm.invoke(prompt.format(topic=topic,difficulty=difficulty))
                parsed_response=fill_in_blank_parser.parse(response.content)
                if not parsed_response.question or not parsed_response.answer:
                    raise ValueError('Invalid question format')
                if '______' not in parsed_response.question:
                    raise ValueError("Question missing blank marker")
                return parsed_response
            except Exception as e:
                if attempt==max_attempts-1:
                    raise RuntimeError(f"Failed to generate valid fill-in-the-blank after {max_attempts} attempts :{str(e)}")
                continue
