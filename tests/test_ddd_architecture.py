"""Comprehensive tests for Domain-Driven Design (DDD) architecture in CodeBone.

Tests:
1. Tactical DDD pattern extraction (Aggregates, Value Objects, Domain Events, Repositories, Domain Services).
2. Strategic Bounded Context inference from path topologies.
3. Domain models (FileRecord, TacticalSymbol, BoundedContext, ArchitectureGraph).
4. Storage persistence, migration, and inverted indexing of DDD entities.
5. Context formatting (overview and search views with DDD elements).
6. Application layer use cases (GetArchitectureContext, ScanProject, ReconcileArchitecture).
"""
import tempfile
import time
from pathlib import Path

import pytest

from src.application.use_cases import (
    GetArchitectureContextUseCase,
    ReconcileArchitectureUseCase,
    ScanProjectUseCase,
)
from src.context_format import overview, search
from src.domain.extractor import extract_tactical_ddd, infer_bounded_context
from src.domain.models import (
    ArchitectureGraph,
    BoundedContext,
    DDDRole,
    FileRecord,
    TacticalSymbol,
)
from src.domain.ports import AnalysisProviderPort, StoragePort
from src.prompts import parse_analysis
from src.providers import FastFallbackProvider
from src.storage import Storage


def test_tactical_extraction_python():
    code = '''
from dataclasses import dataclass
from abc import ABC, abstractmethod

class Order(AggregateRoot):
    """Aggregate Root for managing order state and lifecycle."""
    def __init__(self, order_id: str, total: Money):
        self.order_id = order_id
        self.total = total

@dataclass(frozen=True)
class Money:
    amount: float
    currency: str

class OrderPlacedEvent:
    def __init__(self, order_id: str):
        self.order_id = order_id

class OrderRepository(ABC):
    @abstractmethod
    def save(self, order: Order) -> None:
        pass

class PricingDomainService:
    def calculate_discount(self, order: Order) -> Money:
        return Money(0.0, "USD")
'''
    res = extract_tactical_ddd("src/billing/domain/order.py", code)
    assert "Order" in res["aggregates"]
    assert "Money" in res["value_objects"]
    assert "OrderPlacedEvent" in res["events"]
    assert "OrderRepository" in res["repositories"]
    assert "PricingDomainService" in res["domain_services"]


def test_tactical_extraction_typescript():
    code = '''
export class CustomerAggregate extends AggregateRoot<CustomerId> {
  private name: string;
}

export class EmailAddress extends ValueObject<string> {
  constructor(readonly value: string) { super(value); }
}

export class CustomerRegisteredEvent implements DomainEvent {
  constructor(public readonly customerId: string) {}
}

export interface CustomerRepository {
  findById(id: CustomerId): Promise<CustomerAggregate | null>;
  save(customer: CustomerAggregate): Promise<void>;
}

export class CustomerValidationService {
  public validate(customer: CustomerAggregate): boolean {
    return true;
  }
}
'''
    res = extract_tactical_ddd("contexts/identity/domain/customer.ts", code)
    assert "CustomerAggregate" in res["aggregates"]
    assert "EmailAddress" in res["value_objects"]
    assert "CustomerRegisteredEvent" in res["events"]
    assert "CustomerRepository" in res["repositories"]
    assert "CustomerValidationService" in res["domain_services"]


def test_tactical_extraction_go_rust():
    go_code = '''
package billing

type InvoiceAggregate struct {
    ID string
}

type CurrencyVO struct {
    Code string
}

type InvoicePaidEvent struct {
    InvoiceID string
}

type InvoiceRepository interface {
    Save(inv *InvoiceAggregate) error
}

type TaxDomainService struct {}
'''
    res_go = extract_tactical_ddd("internal/billing/invoice.go", go_code)
    assert "InvoiceAggregate" in res_go["aggregates"]
    assert "CurrencyVO" in res_go["value_objects"]
    assert "InvoicePaidEvent" in res_go["events"]
    assert "InvoiceRepository" in res_go["repositories"]
    assert "TaxDomainService" in res_go["domain_services"]


def test_bounded_context_inference():
    assert infer_bounded_context("src/billing/domain/order.py") == "billing"
    assert infer_bounded_context("apps/inventory/services/stock.py") == "inventory"
    assert infer_bounded_context("packages/shipping/src/courier.ts") == "shipping"
    assert infer_bounded_context("contexts/identity_access/domain/user.py") == "identity_access"
    assert infer_bounded_context("domain/orders/order.py") == "orders"
    assert infer_bounded_context("main.py") is None


def test_domain_models_and_graph():
    rec1 = FileRecord(
        path="src/billing/order.py",
        tables=["orders", "order_items"],
        routes=["POST /orders"],
        events=["OrderPlaced"],
        domains=["billing"],
        summary="Order aggregate root and checkout logic.",
        aggregates=["Order"],
        value_objects=["Money"],
        repositories=["OrderRepository"],
        domain_services=["PricingDomainService"],
        bounded_context="billing",
    )

    rec2 = FileRecord(
        path="src/shipping/shipment.py",
        tables=["shipments"],
        routes=["POST /shipments"],
        events=["ShipmentDispatched"],
        domains=["shipping"],
        summary="Shipment aggregate and carrier dispatch.",
        aggregates=["Shipment"],
        value_objects=["TrackingNumber"],
        repositories=["ShipmentRepository"],
        domain_services=[],
        bounded_context="shipping",
    )

    graph = ArchitectureGraph(project_name="ShopApp")
    graph.add_record(rec1)
    graph.add_record(rec2)

    assert "billing" in graph.bounded_contexts
    assert "shipping" in graph.bounded_contexts
    assert "Order" in graph.aggregates
    assert "Shipment" in graph.aggregates

    summary = graph.summary_metrics()
    assert summary["files_count"] == 2
    assert summary["bounded_contexts_count"] == 2
    assert summary["aggregates_count"] == 2
    assert summary["repositories_count"] == 2


def test_storage_persistence_and_index():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ddd.db"
        storage = Storage(db_path)
        assert isinstance(storage, StoragePort)

        # Upsert with tactical DDD facts
        storage.update_file(
            rel_path="src/billing/order.py",
            raw_output=(
                "TABLES: orders, order_items\n"
                "ROUTES: POST /orders\n"
                "EVENTS: OrderPlacedEvent\n"
                "DOMAINS: billing\n"
                "AGGREGATES: Order\n"
                "VALUE_OBJECTS: Money, Address\n"
                "REPOSITORIES: OrderRepository\n"
                "DOMAIN_SERVICES: PricingService\n"
                "BOUNDED_CONTEXT: billing\n"
                "SUMMARY: Core order management aggregate root."
            ),
            mtime=100.0,
            content_hash="abc123hash",
            source="model",
        )

        record = storage.get_file_record("src/billing/order.py")
        assert record is not None
        assert record.aggregates == ["Order"]
        assert "Money" in record.value_objects
        assert "Address" in record.value_objects
        assert record.repositories == ["OrderRepository"]
        assert record.domain_services == ["PricingService"]
        assert record.bounded_context == "billing"

        # Check entity index inverted maps
        index = storage.entity_index()
        assert "Order" in index.get("aggregates", {})
        assert "Money" in index.get("value_objects", {})
        assert "OrderRepository" in index.get("repositories", {})
        assert "PricingService" in index.get("domain_services", {})
        assert "billing" in index.get("bounded_contexts", {})

        files, _ = storage.view()
        assert len(files) == 1
        assert files[0]["aggregates"] == ["Order"]
        assert files[0]["bounded_context"] == "billing"


def test_context_format_ddd_sections():
    files = [
        {
            "path": "src/billing/order.py",
            "domains": ["billing"],
            "tables": ["orders"],
            "routes": ["POST /orders"],
            "events": ["OrderPlaced"],
            "aggregates": ["Order"],
            "value_objects": ["Money", "Address"],
            "repositories": ["OrderRepository"],
            "domain_services": ["PricingService"],
            "bounded_context": "billing",
            "summary": "Order aggregate root managing cart checkout.",
        }
    ]
    index = {
        "domains": {"billing": ["src/billing/order.py"]},
        "bounded_contexts": {"billing": ["src/billing/order.py"]},
        "aggregates": {"Order": ["src/billing/order.py"]},
        "value_objects": {"Money": ["src/billing/order.py"], "Address": ["src/billing/order.py"]},
        "repositories": {"OrderRepository": ["src/billing/order.py"]},
        "domain_services": {"PricingService": ["src/billing/order.py"]},
        "tables": {"orders": ["src/billing/order.py"]},
        "routes": {"POST /orders": ["src/billing/order.py"]},
        "events": {"OrderPlaced": ["src/billing/order.py"]},
    }

    out_overview = overview("ShopApp", files, index)
    assert "## Bounded Contexts" in out_overview
    assert "- billing (1): src/billing/order.py" in out_overview
    assert "## Entities" in out_overview
    assert "- Aggregates: Order" in out_overview
    assert "- Value Objects: Address, Money" in out_overview
    assert "- Repositories: OrderRepository" in out_overview

    out_search = search("ShopApp", files, index, query="Order")
    assert "[Aggregate Root: Order]" in out_search
    assert "[Context: billing]" in out_search


def test_application_use_cases():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_app_usecases.db"
        storage = Storage(db_path)
        provider = FastFallbackProvider()

        scan_uc = ScanProjectUseCase(storage, provider)
        code = '''
class Account(AggregateRoot):
    def __init__(self, acc_id: str):
        self.acc_id = acc_id

class AccountRepository:
    def find_by_id(self, acc_id: str): pass
'''
        file_rec = scan_uc.analyze_and_record(
            rel_path="src/accounts/domain/account.py",
            code=code,
            mtime=50.0,
            content_hash="hashacc",
        )
        assert file_rec.path == "src/accounts/domain/account.py"
        assert "Account" in file_rec.aggregates
        assert "AccountRepository" in file_rec.repositories
        assert file_rec.bounded_context == "accounts"

        context_uc = GetArchitectureContextUseCase(storage)
        ov = context_uc.get_overview("AccountSystem")
        assert "AccountSystem" in ov
        assert "accounts" in ov
        assert "Account" in ov

        q_res = context_uc.query_context("AccountSystem", query="Account")
        assert "Account" in q_res

        reconcile_uc = ReconcileArchitectureUseCase(storage, provider)
        domains, msg = reconcile_uc.reconcile(delta={"added": ["src/accounts/domain/account.py"]})
        assert isinstance(domains, list)
        assert "accounts" in domains


def test_service_ddd_use_cases_integration():
    from src.config import Config
    from src.service import CodeBoneService
    cfg = Config()
    svc = CodeBoneService(cfg)
    assert isinstance(svc.context_use_case, GetArchitectureContextUseCase)
    assert isinstance(svc.scan_use_case, ScanProjectUseCase)
    assert isinstance(svc.reconcile_use_case, ReconcileArchitectureUseCase)
    assert svc.context_use_case.storage is svc.storage


