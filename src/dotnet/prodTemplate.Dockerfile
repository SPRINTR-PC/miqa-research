# Stage 1: Restore the application and its dependencies
FROM mcr.microsoft.com/dotnet/sdk:${DOTNET_VERSION} AS build
WORKDIR /src

${COPY_PROJECT_FILES_AND_REQUIREMENTS}
COPY ["Miqa.Service.DicomReceiver/Miqa.Service.DicomReceiver.csproj", "Miqa.Service.DicomReceiver/"]
COPY ["Miqa.Infrastructure/Miqa.Infrastructure.csproj", "Miqa.Infrastructure/"]
COPY ["Miqa.Core/Miqa.Core.csproj", "Miqa.Core/"]

RUN dotnet restore "${PROJECT_TO_BUILD}/${PROJECTFILE_FILENAME_FOR_PROJECT_TO_BUILD}"

COPY . .

# Stage 2: Build the application
WORKDIR "/src/${PROJECT_TO_BUILD}"
RUN dotnet build "${PROJECTFILE_FILENAME_FOR_PROJECT_TO_BUILD}" -c Release -o /app/build

# Stage 3: Publish the application
FROM build AS publish
RUN dotnet publish "${PROJECTFILE_FILENAME_FOR_PROJECT_TO_BUILD}" -c Release -o /app/publish /p:UseAppHost=false

# Stage 4: Final optimized image
FROM mcr.microsoft.com/dotnet/runtime:${DOTNET_VERSION} AS final
WORKDIR /app
COPY --from=publish /app/publish .

# Set default environment variables
ENV DOTNET_ENVIRONMENT=Production

# Run the service
ENTRYPOINT ["dotnet", "${PROJECT_TO_BUILD}.dll"]
