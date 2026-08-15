use serde_json::Value;

fn declaration(item: &Value) -> String {
    let params = item["params"].as_array().expect("ABI params");
    let params = if params.is_empty() {
        "void".to_owned()
    } else {
        params
            .iter()
            .map(|p| {
                format!(
                    "{} {}",
                    p["type"].as_str().unwrap(),
                    p["name"].as_str().unwrap()
                )
            })
            .collect::<Vec<_>>()
            .join(", ")
    };
    format!(
        "{} {}({params})",
        item["return"].as_str().unwrap(),
        item["name"].as_str().unwrap()
    )
}

pub fn render_header(manifest: &Value) -> String {
    let mut out = String::from("#ifndef NOTEMELD_AGENT_H\n#define NOTEMELD_AGENT_H\n\n#include <stdint.h>\n\n#ifdef __cplusplus\nextern \"C\" {\n#endif\n\n");
    out.push_str(&format!("#define NOTEMELD_AGENT_ABI_VERSION {}\n#define NOTEMELD_AGENT_SDK_VERSION \"{}\"\n#define NOTEMELD_AGENT_SCHEMA_VERSION \"{}\"\n\n", manifest["abi_version"], manifest["sdk_version"].as_str().unwrap(), manifest["schema_version"].as_str().unwrap()));
    out.push_str("typedef struct AgentRuntimeHandle AgentRuntimeHandle;\n");
    for cb in manifest["callbacks"].as_array().unwrap() {
        let d = declaration(cb);
        let (ret, rest) = d.split_once(' ').unwrap();
        let (name, params) = rest.split_once('(').unwrap();
        out.push_str(&format!("typedef {ret} (*{name})({params};\n"));
    }
    out.push('\n');
    for f in manifest["functions"].as_array().unwrap() {
        out.push_str(&format!(
            "/* ownership: {} | threading: {} | errors: {} */\n",
            f["ownership"].as_str().unwrap(),
            f["threading"].as_str().unwrap(),
            f["errors"].as_str().unwrap()
        ));
        out.push_str(&declaration(f));
        out.push_str(";\n");
    }
    out.push_str("\nenum NotemeldAgentFfiResult {\n");
    let codes = manifest["result_codes"].as_array().unwrap();
    for (i, code) in codes.iter().enumerate() {
        out.push_str(&format!(
            "    NOTEMELD_AGENT_FFI_{} = {}{}\n",
            code[0].as_str().unwrap(),
            code[1],
            if i + 1 == codes.len() { "" } else { "," }
        ));
    }
    out.push_str("};\n\n#ifdef __cplusplus\n}\n#endif\n#endif\n");
    out
}

pub fn render_semantic_udl(manifest: &Value) -> String {
    let mut out = String::from("// Generated semantic declaration of the NoteMeld C ABI.\n// This file is intentionally not presented as UniFFI input.\nnamespace notemeld_agent_abi_v1 {\n");
    for f in manifest["functions"].as_array().unwrap() {
        out.push_str("    // ");
        out.push_str(&declaration(f));
        out.push_str(";\n");
    }
    out.push_str("}\n");
    out
}
