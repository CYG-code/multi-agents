from fastapi import HTTPException, status


class RoomNotFoundError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="房间不存在")


class RoomMemberForbiddenError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="你不是该房间成员")

