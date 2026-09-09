from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.db.engine import Base


class NoteStyle(Base):
    __tablename__ = "note_styles"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True, default="")
    skeleton_html = Column(Text, nullable=False, default="")
    style_constraints = Column(Text, nullable=False, default="{}")
    rule_config = Column(Text, nullable=False, default="{}")
    example_content = Column(Text, nullable=False, default="{}")
    output_formats = Column(Text, nullable=False, default='["markdown"]')
    builtin = Column(Integer, default=0)  # 1 = 系统内置不可删除
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
