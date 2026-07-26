"""Delivery service — dispatch to channel handlers."""
import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import DeliveryListFilter, DeliveryRequest, DeliveryResponse
from ..config import ServeConfig
from ..models.models import DeliveryDao, DeliveryEntity

DELIVERY_SERVICE_COMPONENT_NAME = "serve_delivery_service"
logger = logging.getLogger(__name__)


class DeliveryService(BaseService[DeliveryEntity, DeliveryRequest, DeliveryResponse]):
    name = DELIVERY_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[DeliveryDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: DeliveryDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or DeliveryDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: DeliveryRequest) -> DeliveryResponse:
        response = self._dao.create(request)
        return response

    async def send(self, delivery_id: int) -> DeliveryResponse:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(DeliveryEntity).filter(
                DeliveryEntity.id == delivery_id
            ).first()
            if not entity:
                raise ValueError(f"delivery {delivery_id} not found")
            result: dict = {}
            try:
                if entity.channel == "email":
                    result = self._send_email(entity)
                elif entity.channel == "in_app":
                    result = {"delivered": True, "channel": "in_app"}
                elif entity.channel == "feishu":
                    result = await self._send_via_channel(entity, "feishu")
                elif entity.channel == "dingtalk":
                    result = await self._send_via_channel(entity, "dingtalk")
                else:
                    raise ValueError(f"unsupported channel: {entity.channel}")
                entity.status = "sent"
                entity.sent_at = datetime.now()
                entity.result_json = json.dumps(result, ensure_ascii=False)
            except Exception as e:
                entity.status = "failed"
                entity.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
                logger.exception("delivery send failed")
            session.commit()
            return self._dao.to_response(entity)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _send_email(self, entity: DeliveryEntity) -> dict:
        cfg = self._serve_config
        if not cfg.smtp_host or not cfg.smtp_from:
            return {"delivered": False, "reason": "smtp not configured"}
        msg = MIMEMultipart("alternative")
        msg["From"] = cfg.smtp_from
        msg["To"] = entity.target
        msg["Subject"] = entity.title or "Derisk Delivery"
        msg.attach(MIMEText(entity.message or "", "html", "utf-8"))
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port or 587) as server:
            if cfg.smtp_user and cfg.smtp_password:
                server.login(cfg.smtp_user, cfg.smtp_password)
            server.sendmail(cfg.smtp_from, [entity.target], msg.as_string())
        return {"delivered": True, "channel": "email", "to": entity.target}

    async def _send_via_channel(
        self, entity: DeliveryEntity, channel_type: str
    ) -> dict:
        """Send a delivery through an active IM channel handler.

        Looks up the channel bound to the delivery's workspace with the
        requested channel type, then sends the message through its handler.

        Args:
            entity: The delivery entity to send.
            channel_type: The IM channel type (e.g. feishu, dingtalk).

        Returns:
            Dict with delivery result.
        """
        from derisk.channel.registry import ChannelHandlerRegistry
        from derisk_serve.channel.service.service import (
            Service as ChannelService,
            SERVE_SERVICE_COMPONENT_NAME as CHANNEL_SERVICE_NAME,
        )

        if not entity.workspace_id:
            return {
                "delivered": False,
                "channel": channel_type,
                "reason": "delivery has no workspace_id, cannot resolve channel",
            }

        channel_service: Optional[ChannelService] = None
        try:
            channel_service = self._system_app.get_component(
                CHANNEL_SERVICE_NAME, ChannelService
            )
        except Exception as e:
            logger.warning(f"Failed to resolve channel service: {e}")

        if not channel_service:
            return {
                "delivered": False,
                "channel": channel_type,
                "reason": "channel service not available",
            }

        # Find the active channel bound to this workspace with the right type
        channel_id: Optional[str] = None
        for ch in channel_service.get_enabled_channels():
            if (
                ch.workspace_id == entity.workspace_id
                and ch.channel_type == channel_type
            ):
                channel_id = ch.id
                break

        if not channel_id:
            return {
                "delivered": False,
                "channel": channel_type,
                "reason": f"no active {channel_type} channel bound to workspace {entity.workspace_id}",
            }

        registry = ChannelHandlerRegistry.get_instance()
        handler = registry.get_handler(channel_id)
        if not handler:
            return {
                "delivered": False,
                "channel": channel_type,
                "reason": f"handler not running for channel {channel_id}",
            }

        try:
            send_result = await handler.send_message(
                receiver_id=entity.target,
                content=entity.message or "",
                content_type=entity.format or "text",
            )
            return {
                "delivered": send_result.success,
                "channel": channel_type,
                "message_id": send_result.message_id,
                "error": send_result.error,
            }
        except Exception as e:
            return {
                "delivered": False,
                "channel": channel_type,
                "reason": f"send failed: {e}",
            }

    def list_deliveries(self, f: DeliveryListFilter) -> List[DeliveryResponse]:
        return self._dao.list_by_filter(f)

    def get_by_id(self, delivery_id: int) -> Optional[DeliveryResponse]:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(DeliveryEntity).filter(
                DeliveryEntity.id == delivery_id
            ).first()
            return self._dao.to_response(entity) if entity else None
        finally:
            session.close()
