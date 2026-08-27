const KB =
  1024;

const MB =
  KB * 1024;

const GB =
  MB * 1024;

const TB =
  GB * 1024;


function cleanNumber(
  value: number,
  digits: number
) {

  return value
    .toFixed(digits)
    .replace(
      /\.00$/,
      ""
    );
}


export function formatBytes(
  bytes: number
): string {

  if (
    !Number.isFinite(bytes)
    ||
    bytes <= 0
  ) {

    return "0 B";
  }


  if (bytes >= TB) {

    return (
      cleanNumber(
        bytes / TB,
        2
      )
      +
      " TB"
    );
  }


  if (bytes >= GB) {

    return (
      cleanNumber(
        bytes / GB,
        2
      )
      +
      " GB"
    );
  }


  if (bytes >= MB) {

    return (
      cleanNumber(
        bytes / MB,
        2
      )
      +
      " MB"
    );
  }


  if (bytes >= KB) {

    return (
      cleanNumber(
        bytes / KB,
        2
      )
      +
      " KB"
    );
  }


  return (
    Math.round(bytes)
    +
    " B"
  );
}
