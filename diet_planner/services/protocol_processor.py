import json
import logging
import tempfile
import os
from typing import Dict

from ..models import HistoricNutritionPlan
from ..llm_service import GeminiService

logger = logging.getLogger(__name__)


class ProtocolProcessorService:

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        from llama_index.readers.file import PDFReader

        reader = PDFReader()
        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        try:
            tmp.write(pdf_bytes)
            tmp.flush()
            tmp.close()
            documents = reader.load_data(file=tmp.name)
            return "\n\n".join(doc.text for doc in documents if doc.text.strip())
        finally:
            os.unlink(tmp.name)

    def summarize_protocol(self, extracted_text: str, language_code: str = 'cs') -> dict:
        llm = GeminiService()

        prompt = json.dumps({
            "task": "extract_dietary_protocol_constraints",
            "instructions": [
                "Analyze the following professional diet protocol document.",
                "Extract ALL dietary constraints, rules, and recommendations into structured JSON.",
                "Be thorough — capture every specific food, quantity, timing, and restriction mentioned.",
                f"Return the output in the same language as the document (likely '{language_code}').",
            ],
            "output_format": {
                "calorie_target": {"daily_kcal": None, "notes": ""},
                "macros": {
                    "protein_g": None,
                    "carbs_g": None,
                    "fat_g": None,
                    "fiber_g": None,
                    "notes": ""
                },
                "required_foods": ["list of foods that MUST be included"],
                "forbidden_foods": ["list of foods that MUST be avoided"],
                "limited_foods": [{"food": "", "max_per_day": "", "notes": ""}],
                "meal_timing": {
                    "meals_per_day": None,
                    "eating_window": "",
                    "specific_rules": []
                },
                "medical_conditions": ["relevant conditions mentioned"],
                "supplements": ["any supplements recommended"],
                "hydration": {"daily_liters": None, "notes": ""},
                "special_instructions": ["any other specific instructions"],
                "protocol_summary": "1-2 sentence summary of the overall protocol"
            },
            "document_text": extracted_text[:50000],
        }, ensure_ascii=False)

        result = llm.generate_dietary_plan(
            prompt_text=prompt,
            system_prompt=(
                "You are a clinical nutrition expert. Extract structured dietary constraints "
                "from the provided professional diet protocol document. Return ONLY valid JSON, "
                "no markdown. Be precise and complete — every restriction matters for patient safety."
            ),
            language_code=language_code,
        )

        return result['response']

    def process_protocol(self, plan_id: int) -> None:
        try:
            plan = HistoricNutritionPlan.objects.get(id=plan_id)
        except HistoricNutritionPlan.DoesNotExist:
            logger.error(f"HistoricNutritionPlan {plan_id} not found")
            return

        plan.processing_status = HistoricNutritionPlan.ProcessingStatus.PROCESSING
        plan.save(update_fields=['processing_status'])

        try:
            if not plan.pdf_file:
                raise ValueError("No PDF file attached to this protocol")

            pdf_bytes = bytes(plan.pdf_file)
            extracted_text = self.extract_text_from_pdf(pdf_bytes)

            if not extracted_text.strip():
                raise ValueError(
                    "Could not extract any text from the PDF. "
                    "The file may be a scanned image without OCR."
                )

            plan.extracted_text = extracted_text

            user = plan.user
            language_code = 'cs'
            latest_goal = user.dietary_goals.order_by('-created_at').first()
            if latest_goal:
                language_code = latest_goal.language_code or 'cs'

            constraints = self.summarize_protocol(extracted_text, language_code)
            plan.structured_constraints = json.dumps(constraints, ensure_ascii=False)

            plan.processing_status = HistoricNutritionPlan.ProcessingStatus.COMPLETED
            plan.processing_error = ''
            plan.save(update_fields=[
                'extracted_text', 'structured_constraints',
                'processing_status', 'processing_error',
            ])

            logger.info(f"Protocol {plan_id} processed successfully")

        except Exception as e:
            logger.error(f"Error processing protocol {plan_id}: {e}", exc_info=True)
            plan.processing_status = HistoricNutritionPlan.ProcessingStatus.FAILED
            plan.processing_error = str(e)
            plan.save(update_fields=['processing_status', 'processing_error'])
