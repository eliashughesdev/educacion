/* Aplicación idempotente de pagos en caja. Un reintento con la misma clave devuelve el pago existente. */
CREATE OR ALTER PROCEDURE erp.sp_ApplyPayment
    @InstitutionId INT, @InvoiceId INT, @Amount DECIMAL(18,2), @Method NVARCHAR(14), @Reference NVARCHAR(80),
    @IdempotencyKey NVARCHAR(80), @CashierId INT, @PaymentId INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SELECT @PaymentId = PaymentId FROM erp.Payments WHERE IdempotencyKey = @IdempotencyKey;
    IF @PaymentId IS NOT NULL RETURN;   -- replay idempotente

    BEGIN TRY
        BEGIN TRAN;
        DECLARE @SessionId INT, @StudentId INT, @Code NVARCHAR(20), @Seq INT;
        SELECT @SessionId = CashSessionId FROM erp.CashSessions WHERE CashierId = @CashierId AND Status = N'abierta';
        IF @SessionId IS NULL THROW 50010, N'Debe abrir una caja antes de registrar pagos', 1;

        UPDATE erp.Invoices WITH (ROWLOCK)
           SET Paid = Paid + @Amount, Balance = Balance - @Amount,
               Status = CASE WHEN Balance - @Amount = 0 THEN N'pagada' ELSE N'parcial' END,
               @StudentId = StudentId
         WHERE InvoiceId = @InvoiceId AND InstitutionId = @InstitutionId AND Status <> N'anulada' AND Balance >= @Amount;
        IF @@ROWCOUNT = 0 THROW 50011, N'Monto inválido o factura no disponible', 1;

        SELECT @Code = Code FROM erp.Institutions WHERE InstitutionId = @InstitutionId;
        UPDATE erp.Sequences SET @Seq = LastValue = LastValue + 1 WHERE SeqKey = CONCAT(N'receipt:', @InstitutionId);
        IF @@ROWCOUNT = 0 BEGIN INSERT erp.Sequences (SeqKey, LastValue) VALUES (CONCAT(N'receipt:', @InstitutionId), 1); SET @Seq = 1; END

        INSERT erp.Payments (InstitutionId, ReceiptNumber, InvoiceId, StudentId, CashSessionId, Amount, Method, Reference, IdempotencyKey, Status, CashierId)
        VALUES (@InstitutionId, CONCAT(@Code, N'-R-', RIGHT(CONCAT(N'000000', @Seq), 6)), @InvoiceId, @StudentId, @SessionId,
                @Amount, @Method, @Reference, @IdempotencyKey, N'aplicado', @CashierId);
        SET @PaymentId = SCOPE_IDENTITY();
        COMMIT;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        IF ERROR_NUMBER() IN (2601, 2627)   -- carrera con la misma clave de idempotencia
        BEGIN
            SELECT @PaymentId = PaymentId FROM erp.Payments WHERE IdempotencyKey = @IdempotencyKey;
            RETURN;
        END;
        THROW;
    END CATCH
END
GO

/* Reverso autorizado con separación de funciones. */
CREATE OR ALTER PROCEDURE erp.sp_ReversePayment
    @InstitutionId INT, @PaymentId INT, @UserId INT, @Reason NVARCHAR(300)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRAN;
    DECLARE @InvoiceId INT, @Amount DECIMAL(18,2);
    UPDATE erp.Payments SET Status = N'revertido', ReversedBy = @UserId, ReversedAt = SYSUTCDATETIME(), ReverseReason = @Reason,
           @InvoiceId = InvoiceId, @Amount = Amount
     WHERE PaymentId = @PaymentId AND InstitutionId = @InstitutionId AND Status = N'aplicado' AND CashierId <> @UserId;
    IF @@ROWCOUNT = 0 THROW 50020, N'Pago no reversible (ya revertido o registrado por el mismo usuario)', 1;
    UPDATE erp.Invoices SET Paid = Paid - @Amount, Balance = Balance + @Amount,
           Status = CASE WHEN Paid - @Amount = 0 THEN N'pendiente' ELSE N'parcial' END
     WHERE InvoiceId = @InvoiceId;
    COMMIT;
END
GO
