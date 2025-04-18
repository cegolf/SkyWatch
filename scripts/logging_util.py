


def get_last_log_lines(log_file, num_lines=10):
    """Get the last N lines from a log file"""
    try:
        # Method that works for both small and large files
        with open(log_file, 'r') as file:
            # Use a deque with maxlen to efficiently get the last N lines
            from collections import deque
            last_lines = deque(maxlen=num_lines)
            
            for line in file:
                last_lines.append(line.strip())
            
            return '\n'.join(last_lines)
    except Exception as e:
        return f"Error reading log file: {str(e)}"