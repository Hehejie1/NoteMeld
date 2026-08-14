use std::sync::{Arc, Mutex};

use agent_events::{AgentError, AgentErrorCode};
use agent_model::{
    invoke_model, ModelChunk, ModelChunkSink, ModelCompletion, ModelDriver, ModelRequest,
    ModelUsage,
};
use async_trait::async_trait;
use serde_json::json;

struct OrderedDriver;

#[async_trait]
impl ModelDriver for OrderedDriver {
    async fn stream(
        &self,
        request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        assert_eq!(request.messages.len(), 1);
        sink.emit(ModelChunk::ContentDelta {
            delta: "alpha".to_owned(),
        })
        .await?;
        sink.emit(ModelChunk::ContentDelta {
            delta: "beta".to_owned(),
        })
        .await?;
        sink.emit(ModelChunk::ContentDelta {
            delta: "gamma".to_owned(),
        })
        .await?;

        Ok(ModelCompletion {
            content: "alphabetagamma".to_owned(),
            tool_calls: Vec::new(),
            finish_reason: "stop".to_owned(),
            usage: ModelUsage {
                input_tokens: 11,
                output_tokens: 7,
                cache_read_tokens: 3,
                cache_write_tokens: 2,
            },
        })
    }
}

#[tokio::test]
async fn stream_preserves_chunk_order_and_propagates_usage() {
    let observed = Arc::new(Mutex::new(Vec::new()));
    let observer = Arc::clone(&observed);
    let sink = ModelChunkSink::new(move |chunk| {
        let observer = Arc::clone(&observer);
        async move {
            let ModelChunk::ContentDelta { delta } = chunk;
            observer.lock().unwrap().push(delta);
            Ok(())
        }
    });
    let request = ModelRequest::new(vec![agent_model::ModelMessage {
        role: "user".to_owned(),
        content: json!("hello"),
    }]);

    let completion = OrderedDriver.stream(request, sink).await.unwrap();

    assert_eq!(*observed.lock().unwrap(), ["alpha", "beta", "gamma"]);
    assert_eq!(completion.content, "alphabetagamma");
    assert_eq!(completion.usage.input_tokens, 11);
    assert_eq!(completion.usage.output_tokens, 7);
    assert_eq!(completion.usage.cache_read_tokens, 3);
    assert_eq!(completion.usage.cache_write_tokens, 2);
    assert_eq!(completion.usage.total_tokens(), 18);
}

struct SinkAwareDriver;

#[async_trait]
impl ModelDriver for SinkAwareDriver {
    async fn stream(
        &self,
        _request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        sink.emit(ModelChunk::ContentDelta {
            delta: "first".to_owned(),
        })
        .await?;
        sink.emit(ModelChunk::ContentDelta {
            delta: "second".to_owned(),
        })
        .await?;
        unreachable!("the second observer call must fail")
    }
}

#[tokio::test]
async fn stream_surfaces_the_first_sink_failure_without_observing_later_chunks() {
    let observed = Arc::new(Mutex::new(Vec::new()));
    let observer = Arc::clone(&observed);
    let sink = ModelChunkSink::new(move |chunk| {
        let observer = Arc::clone(&observer);
        async move {
            let ModelChunk::ContentDelta { delta } = chunk;
            observer.lock().unwrap().push(delta.clone());
            if delta == "second" {
                Err(AgentError::new(
                    AgentErrorCode::SdkInternalError,
                    "model chunk observer failed",
                ))
            } else {
                Ok(())
            }
        }
    });

    let error = SinkAwareDriver
        .stream(ModelRequest::new(Vec::new()), sink.clone())
        .await
        .unwrap_err();
    assert_eq!(error.code, AgentErrorCode::SdkInternalError);
    assert_eq!(error.message, "model chunk observer failed");

    let repeated = sink
        .emit(ModelChunk::ContentDelta {
            delta: "third".to_owned(),
        })
        .await
        .unwrap_err();
    assert_eq!(repeated, error);
    assert_eq!(*observed.lock().unwrap(), ["first", "second"]);
}

struct CancellableDriver;

#[async_trait]
impl ModelDriver for CancellableDriver {
    async fn stream(
        &self,
        request: ModelRequest,
        _sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        request.cancellation.cancelled().await;
        Err(AgentError::new(
            AgentErrorCode::Cancelled,
            "model request cancelled",
        ))
    }
}

#[tokio::test]
async fn model_request_propagates_explicit_cancellation() {
    let request = ModelRequest::new(Vec::new());
    let cancellation = request.cancellation.clone();
    let task = tokio::spawn(async move {
        CancellableDriver
            .stream(request, ModelChunkSink::discard())
            .await
    });

    cancellation.cancel();

    let error = task.await.unwrap().unwrap_err();
    assert_eq!(error.code, AgentErrorCode::Cancelled);
    assert_eq!(error.message, "model request cancelled");
}

struct IgnoredSinkFailureDriver;

#[async_trait]
impl ModelDriver for IgnoredSinkFailureDriver {
    async fn stream(
        &self,
        _request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        let _ignored = sink
            .emit(ModelChunk::ContentDelta {
                delta: "ignored".to_owned(),
            })
            .await;
        Ok(ModelCompletion {
            content: "driver returned success".to_owned(),
            tool_calls: Vec::new(),
            finish_reason: "stop".to_owned(),
            usage: ModelUsage::default(),
        })
    }
}

#[tokio::test]
async fn invocation_boundary_surfaces_sink_failure_even_if_driver_ignores_it() {
    let sink = ModelChunkSink::new(|_chunk| async {
        Err(AgentError::new(
            AgentErrorCode::SdkInternalError,
            "model chunk observer failed",
        ))
    });

    let error = invoke_model(
        &IgnoredSinkFailureDriver,
        ModelRequest::new(Vec::new()),
        sink,
    )
    .await
    .unwrap_err();

    assert_eq!(error.code, AgentErrorCode::SdkInternalError);
    assert_eq!(error.message, "model chunk observer failed");
}
