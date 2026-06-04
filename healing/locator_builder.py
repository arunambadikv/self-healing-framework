def build_locator(page_or_frame, candidate: dict):
    ltype = candidate.get("type")
    
    if ltype == "test_id":
        return page_or_frame.get_by_test_id(candidate.get("value"))
    elif ltype == "role":
        return page_or_frame.get_by_role(candidate.get("role"), name=candidate.get("name"))
    elif ltype == "label":
        return page_or_frame.get_by_label(candidate.get("value"))
    elif ltype == "text":
        exact = candidate.get("exact", False)
        return page_or_frame.get_by_text(candidate.get("value"), exact=exact)
    elif ltype == "placeholder":
        return page_or_frame.get_by_placeholder(candidate.get("value"))
    elif ltype == "css":
        return page_or_frame.locator(candidate.get("value"))
    elif ltype == "frame_css":
        frame = candidate.get("frame")
        value = candidate.get("value")
        return page_or_frame.frame_locator(frame).locator(value)
    else:
        raise ValueError(f"Unknown locator type: {ltype}")
