from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.models import MarketingAttribution


class ConsentView(APIView):
    """Record a post-authentication consent change (opt-in or withdrawal)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        consent = bool(request.data.get("consent"))
        version = str(request.data.get("version", ""))[:20]
        attr, _ = MarketingAttribution.objects.get_or_create(user=request.user)
        attr.marketing_consent = consent
        attr.consent_version = version
        attr.consent_at = timezone.now()
        attr.save(update_fields=["marketing_consent", "consent_version",
                                 "consent_at", "updated_at"])
        return Response({"status": "success", "data": {"consent": consent},
                        "error": None})
