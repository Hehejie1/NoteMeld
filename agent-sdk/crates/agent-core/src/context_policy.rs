use crate::AgentMessage;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ContextPolicy { pub context_window_tokens: usize, pub output_reserve_tokens: usize, pub safety_reserve_tokens: usize }
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ContextBudget { pub input_tokens: usize, pub available_tokens: usize }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContextTrimDiagnostic { pub removed_messages: usize, pub estimated_input_tokens: usize }
impl Default for ContextPolicy { fn default()->Self { Self{context_window_tokens:4096,output_reserve_tokens:1024,safety_reserve_tokens:410} } }
impl ContextPolicy {
 pub fn budget(&self)->ContextBudget { ContextBudget{input_tokens:0,available_tokens:self.context_window_tokens.saturating_sub(self.output_reserve_tokens+self.safety_reserve_tokens)} }
 pub fn trim_messages(&self,messages:&[AgentMessage])->(Vec<AgentMessage>,Option<ContextTrimDiagnostic>) { let available=self.budget().available_tokens; let mut kept=messages.to_vec(); let mut estimated=estimate(&kept); let original=kept.len(); while estimated>available&&kept.len()>2 { kept.remove(1); estimated=estimate(&kept); } let diag=(original!=kept.len()).then_some(ContextTrimDiagnostic{removed_messages:original-kept.len(),estimated_input_tokens:estimated}); (kept,diag) }
}
fn estimate(messages:&[AgentMessage])->usize { messages.iter().map(|m|serde_json::to_vec(m).map(|v|(v.len()+2)/3+4).unwrap_or(0)).sum() }
