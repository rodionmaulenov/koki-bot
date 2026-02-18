from supabase import AsyncClient

from models.payment_receipt import PaymentReceipt


class PaymentReceiptRepository:
    def __init__(self, supabase: AsyncClient) -> None:
        self._supabase = supabase

    async def create(
        self,
        course_id: int,
        accountant_id: int,
        receipt_file_id: str,
        amount: int | None = None,
    ) -> PaymentReceipt:
        data: dict = {
            "course_id": course_id,
            "accountant_id": accountant_id,
            "receipt_file_id": receipt_file_id,
        }
        if amount is not None:
            data["amount"] = amount
        response = await (
            self._supabase.schema("kok")
            .table("payment_receipts")
            .insert(data)
            .execute()
        )
        return PaymentReceipt(**response.data[0])

    async def get_by_course_id(self, course_id: int) -> PaymentReceipt | None:
        response = await (
            self._supabase.schema("kok")
            .table("payment_receipts")
            .select("id, course_id, accountant_id, receipt_file_id, amount, created_at")
            .eq("course_id", course_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return PaymentReceipt(**response.data[0])
        return None
