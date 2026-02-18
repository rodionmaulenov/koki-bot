-- RPC function: create user + document + course in one transaction
-- If any INSERT fails, all changes are rolled back automatically.

-- Drop old function variants
DROP FUNCTION IF EXISTS kok.create_user_with_documents(varchar, integer, text, text, integer, text, text, text, varchar);
DROP FUNCTION IF EXISTS public.create_user_with_documents(varchar, integer, text, text, integer, text, text, text, varchar);
DROP FUNCTION IF EXISTS public.create_user_with_documents(varchar, integer, text, text, integer, text, text, text, varchar, varchar, integer);

CREATE OR REPLACE FUNCTION public.create_user_with_documents(
    p_name varchar,
    p_manager_id integer,
    p_passport_file_id text,
    p_receipt_file_id text,
    p_receipt_price integer,
    p_card_file_id text,
    p_card_number text,
    p_card_holder_name text,
    p_invite_code varchar,
    p_birth_date varchar DEFAULT NULL,
    p_existing_user_id integer DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id integer;
    v_course_id integer;
    v_created_at timestamptz;
BEGIN
    -- 1. Create or reuse user
    IF p_existing_user_id IS NOT NULL THEN
        v_user_id := p_existing_user_id;
    ELSE
        INSERT INTO kok.users (name, manager_id, birth_date)
        VALUES (p_name, p_manager_id, p_birth_date)
        RETURNING id INTO v_user_id;
    END IF;

    -- 2. Create document
    INSERT INTO kok.documents (
        user_id, manager_id,
        passport_file_id, receipt_file_id, receipt_price,
        card_file_id, card_number, card_holder_name
    ) VALUES (
        v_user_id, p_manager_id,
        p_passport_file_id, p_receipt_file_id, p_receipt_price,
        p_card_file_id, p_card_number, p_card_holder_name
    );

    -- 3. Create course
    INSERT INTO kok.courses (user_id, invite_code)
    VALUES (v_user_id, p_invite_code)
    RETURNING id, created_at INTO v_course_id, v_created_at;

    -- Return course data (matches Course model fields)
    RETURN jsonb_build_object(
        'id', v_course_id,
        'user_id', v_user_id,
        'status', 'setup',
        'invite_code', p_invite_code,
        'invite_used', false,
        'created_at', v_created_at
    );
END;
$$;
