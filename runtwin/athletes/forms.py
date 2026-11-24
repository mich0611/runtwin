from django import forms

from .models import WellbeingCheckIn


class WellbeingCheckInForm(forms.ModelForm):
    class Meta:
        model = WellbeingCheckIn
        fields = ["sleep_quality", "fatigue", "soreness", "knee_pain", "motivation", "notes"]
        labels = {
            "sleep_quality": "睡眠品質（1–5）",
            "fatigue": "疲勞（0–10）",
            "soreness": "肌肉痠痛（0–10）",
            "knee_pain": "膝部疼痛（0–10）",
            "motivation": "訓練動機（1–5）",
            "notes": "備註",
        }
        widgets = {
            "sleep_quality": forms.NumberInput(attrs={"min": 1, "max": 5, "inputmode": "numeric", "placeholder": "1–5"}),
            "fatigue": forms.NumberInput(attrs={"min": 0, "max": 10, "inputmode": "numeric", "placeholder": "0–10"}),
            "soreness": forms.NumberInput(attrs={"min": 0, "max": 10, "inputmode": "numeric", "placeholder": "0–10"}),
            "knee_pain": forms.NumberInput(attrs={"min": 0, "max": 10, "inputmode": "numeric", "placeholder": "0–10"}),
            "motivation": forms.NumberInput(attrs={"min": 1, "max": 5, "inputmode": "numeric", "placeholder": "1–5"}),
            "notes": forms.Textarea(attrs={"rows": 5, "placeholder": "例如：最近睡眠較少、右小腿緊、工作壓力偏高…"}),
        }

    def clean(self):
        cleaned = super().clean()
        ranges = {"sleep_quality": (1, 5), "fatigue": (0, 10), "soreness": (0, 10), "knee_pain": (0, 10), "motivation": (1, 5)}
        for field, (low, high) in ranges.items():
            value = cleaned.get(field)
            if value is not None and not low <= value <= high:
                self.add_error(field, f"請輸入 {low} 到 {high}。")
        return cleaned
